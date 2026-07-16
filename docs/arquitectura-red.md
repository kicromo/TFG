# Arquitectura de Red — Fases de Despliegue

Este documento describe la evolución de la arquitectura de red del sistema a lo largo de las tres fases de despliegue. La lógica de la aplicación (capturer, sender, receiver) no cambia entre fases; solo cambia la capa de red.

---

## Fase 0 — LAN local (completada)

Entorno de desarrollo. El RPi5 y el PC están en la misma red local. No hay cifrado de red; el tráfico TCP va en claro por la LAN.

```
┌─────────────────────────────────────────┐
│  RED LOCAL (192.168.1.0/24)             │
│                                         │
│  ┌──────────────┐      ┌─────────────┐  │
│  │   RPi5       │      │     PC      │  │
│  │ 192.168.1.38 │      │ 192.168.1.X │  │
│  │              │      │             │  │
│  │ capturer.py  │      │ receiver.py │  │
│  │ sender.py    │─────►│ :9000       │  │
│  │              │ TCP  │             │  │
│  │              │      │ storage/    │  │
│  └──────────────┘      └─────────────┘  │
│                                         │
│  Router doméstico (España)              │
└─────────────────────────────────────────┘

Protocolo : TCP directo
Cifrado   : Ninguno
Config    : server.host = "192.168.1.X"
Limitación: Solo funciona en la misma red local
```

---

## Fase 1 — WireGuard en LAN (actual)

Se añade una capa VPN sobre la red local. El sender y el receiver no saben que hay una VPN; solo ven las IPs del túnel (10.0.0.x). El cifrado es transparente para la aplicación.

```
┌──────────────────────────────────────────────────────────────┐
│  RED LOCAL (192.168.1.0/24)                                  │
│                                                              │
│  ┌───────────────────────┐      ┌───────────────────────┐   │
│  │       RPi5            │      │          PC           │   │
│  │  LAN: 192.168.1.38    │      │  LAN: 192.168.1.49    │   │
│  │  VPN: 10.0.0.2        │      │  VPN: 10.0.0.1        │   │
│  │                       │      │                       │   │
│  │  [capturer.py]        │      │  [receiver.py :9000]  │   │
│  │  [sender.py]          │      │  [event_logger.py]    │   │
│  │       │               │      │         ▲             │   │
│  │       │ TCP           │      │         │ TCP         │   │
│  │       ▼               │      │         │             │   │
│  │  [wg0: WireGuard]     │      │  [wg0: WireGuard]     │   │
│  │  ChaCha20-Poly1305    │      │  ChaCha20-Poly1305    │   │
│  │  Curve25519 keys      │      │  ListenPort: 51820    │   │
│  └──────────┬────────────┘      └──────────▲────────────┘   │
│             │    UDP cifrado               │                 │
│             └──────────── :51820 ──────────┘                 │
│                                                              │
│  Router doméstico (España)                                   │
└──────────────────────────────────────────────────────────────┘

Protocolo : TCP dentro de túnel WireGuard (UDP cifrado)
Cifrado   : ChaCha20-Poly1305 + autenticación Curve25519
Config    : server.host = "10.0.0.1"  (IP del túnel, nunca cambia)
Limitación: La IP física del PC puede cambiar por DHCP
            → Solución: reserva DHCP en el router
```

### Servicios systemd activos en RPi5 (Fase 1)

```
systemd (arranque)
├── wg-quick@wg0.service        → túnel WireGuard
├── camera-capture.service      → capturer.py + FFmpeg
├── camera-sender.service       → sender.py (LIVE/BUFFER)
└── camera-sync.service         → sync_scheduler.py (medianoche)
```

---

## Fase 1.5 — DuckDNS + port forwarding (implementado, 2026-07-16)

Solución intermedia gratuita para el problema de IP pública dinámica, implementada antes de pasar a Fase 2. No cambia la arquitectura del túnel ni el código de la aplicación; solo resuelve cómo el RPi5 localiza el endpoint del PC cuando la IP pública de Movistar cambia.

```
┌──────────────────────────────────────────────────────────────┐
│  RED LOCAL (192.168.1.0/24)                                  │
│                                                              │
│  ┌───────────────────────┐      ┌───────────────────────┐   │
│  │       RPi5            │      │          PC           │   │
│  │  VPN: 10.0.0.2        │      │  VPN: 10.0.0.1        │   │
│  │                       │      │  LAN: 192.168.1.49    │   │
│  │  Endpoint:            │      │  WAN: rpidamh.        │   │
│  │  rpidamh.duckdns.org  │      │       duckdns.org     │   │
│  │  :51820               │      │  (UDP 51820 abierto)  │   │
│  └──────────┬────────────┘      └──────────▲────────────┘   │
│             │    UDP cifrado               │                 │
│             └──────────── :51820 ──────────┘                 │
│                                                              │
│  Router Askey RTF8225VW                                      │
│  Port forwarding: UDP 51820 WAN → 192.168.1.49:51820         │
└──────────────────────────────────────────────────────────────┘

                          Internet
                              │
             ┌────────────────┴──────────────────┐
             │         DuckDNS (duckdns.org)      │
             │  rpidamh.duckdns.org → IP actual   │
             │  Actualización: cada 5 min (cron)  │
             └───────────────────────────────────┘

Protocolo : TCP dentro de túnel WireGuard (UDP cifrado)
Cifrado   : ChaCha20-Poly1305 + autenticación Curve25519
Config    : server.host = "10.0.0.1"  (sin cambios en la aplicación)
            Endpoint del RPi5 = rpidamh.duckdns.org:51820
Limitación: depende de que Movistar no use CGNAT ni bloquee UDP 51820
```

**Componentes de la Fase 1.5**:

| Componente | Detalle |
|-----------|---------|
| Subdominio DuckDNS | `rpidamh.duckdns.org` |
| Script de actualización | `/home/damh/.duckdns/update.sh` (cron cada 5 min) |
| Port forwarding | UDP 51820 (WAN) → 192.168.1.49 (LAN) |
| Endpoint RPi5 | `rpidamh.duckdns.org:51820` (antes: IP física) |

---

## Fase 2 — WireGuard con VPS relay (pendiente)

Cuando el RPi5 esté en Bolivia y el PC en España, necesitan un punto de encuentro con IP pública fija. Un VPS (servidor virtual en la nube) actúa como hub WireGuard accesible desde cualquier parte del mundo.

```
┌────────────────────────────────────────────────────────────────────┐
│  INTERNET                                                          │
│                                                                    │
│  ┌──────────────┐         ┌─────────────────┐    ┌─────────────┐  │
│  │    RPi5      │         │   VPS (Hetzner  │    │     PC      │  │
│  │   Bolivia    │         │   o similar)    │    │   España    │  │
│  │              │         │                 │    │             │  │
│  │ VPN:10.0.0.2 │         │  IP pública     │    │ VPN:10.0.0.1│  │
│  │              │◄────────│  fija y estable │────►│             │  │
│  │ capturer.py  │  WG UDP │  hub WireGuard  │ WG │ receiver.py │  │
│  │ sender.py    │         │  :51820         │ UDP│ :9000       │  │
│  │              │         │                 │    │             │  │
│  └──────────────┘         └─────────────────┘    └─────────────┘  │
│                                                                    │
│       ~200ms RTT Bolivia↔España                                    │
└────────────────────────────────────────────────────────────────────┘

Protocolo : TCP dentro de túnel WireGuard multi-hop
Cifrado   : ChaCha20-Poly1305 en todo el trayecto
Config    : server.host = "10.0.0.1"  (sin cambios en la aplicación)
            Endpoint del RPi5 = IP pública del VPS (fija para siempre)
Coste VPS : ~4-6 EUR/mes (Hetzner CX11 o similar)
```

### ¿Es peligroso exponer un VPS?

El VPS solo expone el puerto 51820/UDP para WireGuard. Al estar protegido por criptografía de clave pública (Curve25519), un atacante que capture el tráfico UDP no puede ni descifrarlo ni inyectar paquetes falsos. Solo los peers con la clave privada correcta pueden participar en el túnel.

Medidas de seguridad estándar para el VPS:

| Medida | Por qué |
|--------|---------|
| SSH solo con clave pública (sin contraseña) | Evita ataques de fuerza bruta |
| UFW: solo 22/TCP y 51820/UDP abiertos | Superficie de ataque mínima |
| Usuario sin privilegios para la aplicación | El proceso receiver no corre como root |
| Claves WireGuard rotadas periódicamente | Limita el impacto si una clave se filtra |

---

## Comparativa de fases

| Aspecto | Fase 0 | Fase 1 | Fase 1.5 | Fase 2 |
|---------|--------|--------|----------|--------|
| Ubicación RPi5 | España (LAN) | España (LAN) | España (LAN) | Bolivia (internet) |
| Cifrado tráfico | No | WireGuard | WireGuard | WireGuard |
| Localización del PC | IP física (cambia) | IP túnel (fija) | `rpidamh.duckdns.org` | Túnel via VPS (fija) |
| IP pública del PC | N/A | N/A | Dinámica, resuelta por DuckDNS | VPS con IP fija |
| Fallo de red | Buffer local | Buffer local | Buffer local | Buffer local |
| Cambio en config.yaml | IP LAN | 10.0.0.1 | 10.0.0.1 (sin cambio) | 10.0.0.1 (sin cambio) |
| Cambio en código | Ninguno | Ninguno | Ninguno | Ninguno |
| Coste adicional | 0 EUR | 0 EUR | 0 EUR | ~5 EUR/mes |

El principio de diseño se mantiene en todas las fases: la aplicación solo conoce `(host, port)`. La capa de red es completamente opaca para el sender y el receiver.
