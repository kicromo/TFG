# Decisiones Técnicas

## Estado actual: Fase 0 completada — LAN local (RPi5 + PC en la misma red, España)

---

## DT-001: Protocolo de transporte de red

**Fecha**: 2026-04-14
**Estado**: Decidido

**Problema**: Transmitir vídeo desde Bolivia hasta España cruzando múltiples NATs y redes no controladas.

**Decisión**: WireGuard VPN como capa de red segura + TCP para el envío de segmentos sobre el túnel.

**Justificación**:
- WireGuard opera en el kernel de Linux, con mínimo overhead de CPU (importante para RPi5 con 1 GB RAM).
- Autenticación por par de claves (curvas elípticas Curve25519): no hay contraseñas en tránsito.
- Cifrado ChaCha20-Poly1305: eficiente en hardware sin AES-NI (como ARM Cortex-A76).
- UDP subyacente: funciona bien con NAT; el traversal se gestiona con keep-alive.
- IP pública requerida en al menos un extremo: el PC en España o un VPS futuro.

**Alternativa descartada**: Tailscale. Mismo protocolo WireGuard pero la coordinación de claves ocurre en servidores de terceros, lo que viola el objetivo de control total sobre la infraestructura.

---

## DT-002: Método de transmisión de vídeo

**Fecha**: 2026-04-14
**Estado**: Decidido

**Problema**: Diseñar una transmisión robusta ante desconexiones de red (la red boliviana puede ser inestable o caer durante horas).

**Decisión**: Segmentos MPEG-TS de 3 segundos generados por FFmpeg, enviados individualmente con verificación SHA-256.

**Justificación**:
- Cada segmento es atómico: si falla el envío, solo se reintenta ese segmento, no toda la sesión.
- Buffer local natural: los `.ts` se guardan en disco hasta que haya conectividad.
- Compatible con HLS: en el futuro el servidor puede servir una playlist `.m3u8` directamente a un reproductor (VLC, hls.js).
- FFmpeg tiene soporte nativo de segmentación: `-f segment -segment_time 3`.

**Latencia estimada**: 3 a 8 segundos (duración del segmento más codificación más red). Aceptable para monitorización de seguridad; no es videoconferencia.

---

## DT-003: Codec de vídeo y parámetros de captura

**Fecha**: 2026-04-28 (decisión inicial) / revisado 2026-05-06 (validado con hardware)
**Estado**: Decidido y validado

**WebCam**: Logitech C270 HD Webcam en `/dev/video0`

**Hallazgo crítico (2026-04-28)**: La cámara soporta dos formatos de entrada:
- `YUYV` (raw): a 1280×720 solo alcanza 7.5 fps. El bus USB no da más ancho de banda con datos sin comprimir.
- `MJPG` (comprimido en cámara): a 1280×720 alcanza 30 fps. La cámara comprime internamente antes de enviar por USB.

**Decisión**: Usar `MJPG` como formato de captura. FFmpeg recibe MJPG y lo recodifica a H.264.

**Hallazgo crítico (2026-05-06)**: `h264_v4l2m2m` no funciona en RPi5. El RPi5 tiene una arquitectura de vídeo diferente al RPi4: los nodos `/dev/video20`–`/dev/video35` son del ISP de imagen (PiSP Backend), no un encoder H.264 accesible por V4L2 M2M. Error: `Could not find a valid device`.

**Decisión revisada**: Usar `libx264` (software) con `-preset ultrafast -tune zerolatency`. El RPi5 (Cortex-A76 × 4 a 2.4 GHz) gestiona 720p a 15 fps con un 6% de CPU total, dejando margen suficiente.

**Parámetros FFmpeg definitivos**:
```
Entrada:  -f v4l2 -input_format mjpeg -video_size 1280x720 -framerate 15 -i /dev/video0
Salida:   -c:v libx264 -preset ultrafast -tune zerolatency -b:v 1000k
GOP:      -g 45 -keyint_min 45   (15 fps x 3 s = keyframe cada 3 s, corte limpio de segmento)
```

---

## DT-004: Gestión del buffer local

**Fecha**: 2026-04-28
**Estado**: Implementado

**Problema**: Los segmentos deben almacenarse de forma fiable en disco cuando no hay conectividad.

**Decisión**: Tres directorios con responsabilidades distintas:
- `staging/` (`/var/camera-buffer/staging/`): FFmpeg escribe el segmento activo aquí.
- `ready/` (`/var/camera-buffer/ready/`): segmentos completos listos para el sender en modo LIVE.
- `archive/` (`/home/pi_damh/buffer/`): segmentos durante caídas de red; enviados por el scheduler nocturno.

**Política de limpieza**: eliminar segmentos más antiguos cuando el disco supere el 80% de uso (configurable en `buffer.max_disk_percent`). Límite máximo de 5000 segmentos (~4.2 horas de vídeo a 1 segmento/3 s).

---

## DT-005: Seguridad

**Fecha**: 2026-04-14
**Estado**: Parcialmente implementado (SHA-256 y log de eventos activos; WireGuard y JWT pendientes)

| Amenaza (STRIDE) | Mecanismo de mitigación | Estado |
|------------------|------------------------|--------|
| Spoofing de nodo | Claves públicas WireGuard pre-compartidas | Pendiente (Fase 1) |
| Tampering de segmentos | SHA-256 por segmento, verificado en recepción | Implementado y probado |
| Repudio | Log inmutable de eventos en JSON Lines con timestamp | Implementado |
| Information Disclosure | Todo el tráfico cifrado por WireGuard | Pendiente (Fase 1) |
| DoS | Buffer con límite en disco; rate limiting futuro | Parcial |
| Elevation of Privilege | JWT con expiración corta; bcrypt en credenciales | Pendiente |

**Test de integridad ejecutado (2026-06-21)**: `tests/test_sha256_integrity.py`

| Vector de ataque probado | Resultado del test |
|-------------------------|-------------------|
| Hash falso en la cabecera (tampering de metadatos) | Detectado y rechazado |
| Datos manipulados en tránsito (bit-flip post-firma) | Detectado y rechazado |
| Ambos incidentes registrados en events.jsonl | Auditoria correcta |

---

## DT-006: Estrategia de despliegue por fases

**Fecha**: 2026-04-14
**Estado**: Decidido; Fase 0 completada

**Problema**: El objetivo final (Bolivia hacia España) no es el punto de partida. Empezar con VPN complica el desarrollo y el debugging inicial.

**Decisión**: Desarrollo en tres fases con la misma base de código:

| Fase | Red | Cambio requerido |
|------|-----|-----------------|
| 0 — LAN local | TCP directo (192.168.x.x) | Solo configurar IP del PC en config.yaml |
| 1 — Redes distintas | WireGuard entre RPi5 y PC | Instalar WireGuard, cambiar IP en config.yaml |
| 2 — Internacional | WireGuard con VPS relay | Cambiar IP endpoint a VPS |

**Principio de diseño**: La capa de red es completamente transparente para la lógica de la aplicación. El `Sender` solo conoce `(host, port)` leído de `config.yaml`. No hay código específico de VPN en la lógica de negocio.

---

## DT-009: Configuración WireGuard — lecciones del despliegue en LAN

**Fecha**: 2026-07-05
**Estado**: Implementado (Fase 1 — LAN); pendiente migración a IP pública (Fase 2)

**Problema**: Al configurar el túnel WireGuard, el RPi5 no establecía handshake con el PC. El sender enviaba paquetes pero el PC no recibía nada.

**Causa raíz**: el `Endpoint` del RPi5 apuntaba a `192.168.1.50`, IP que no pertenecía al PC en ese momento. El PC tenía `192.168.1.37` (cable) y `192.168.1.47` (WiFi), asignadas por DHCP.

**Diagnóstico empleado**:

```bash
# En el PC — capturar UDP en la interfaz física (no en any, sino en eno1)
sudo tcpdump -i eno1 -n udp port 51820
# Resultado: 0 paquetes capturados → los paquetes no llegaban al PC
```

```bash
# Verificar IP real del PC
ip addr show | grep '192.168'
```

El tcpdump reveló que el problema era de red, no de claves. Si los paquetes hubieran llegado pero el handshake fallara, el tcpdump mostraría paquetes y la causa sería un mismatch de claves públicas.

**Resolución**: actualizar `Endpoint` en `/etc/wireguard/wg0.conf` del RPi5 con la IP correcta y reiniciar `wg-quick`.

**Decisión de diseño derivada**: en Fase 2, el Endpoint del RPi5 apuntará a la IP pública del VPS (fija), eliminando el problema de IP dinámica por DHCP. Para la Fase 1 (LAN), se recomienda reserva DHCP en el router para la MAC del PC.

**Flujo de diagnóstico para futuros fallos de túnel**:

| Síntoma en `wg show` | Diagnóstico | Acción |
|----------------------|------------|--------|
| `transfer: X sent, 0 received` | Paquetes salen pero no llegan | tcpdump en el receptor: ¿llegan los paquetes? |
| tcpdump: 0 paquetes | Endpoint incorrecto o firewall pre-WireGuard | Verificar IP del receptor y reglas UFW |
| tcpdump: paquetes visibles pero sin handshake | Mismatch de claves públicas | Regenerar claves y actualizar configs |
| `latest handshake: X seconds ago` ausente | No ha habido handshake | Verificar que el iniciador tiene `PersistentKeepalive` |

---

## DT-010: DNS dinámico para IP pública dinámica del PC

**Fecha**: 2026-07-16
**Estado**: Implementado (Fase 1.5)

**Problema**: El PC tiene IP pública dinámica asignada por Movistar. Cuando el RPi5 esté en Bolivia, necesitará conectar al endpoint WireGuard del PC usando un hostname fijo, independientemente de cuál sea la IP pública en ese momento. Sin un mecanismo de actualización DNS, cualquier cambio de IP rompe el túnel sin posibilidad de corrección remota.

**Alternativas evaluadas**:

| Opción | Coste | Pros | Contras |
|--------|-------|------|---------|
| VPS con IP pública fija (Hetzner, etc.) | ~5 EUR/mes | IP siempre fija, control total | Coste recurrente; añade un hop en la ruta |
| Oracle Cloud Free Tier (VPS gratuito) | 0 EUR | Gratuito; IP fija | Puede cambiar de política; más complejo de mantener |
| Tailscale | 0 EUR (plan personal) | Simple de configurar | La coordinación de claves pasa por servidores de terceros (fuera del control del proyecto) |
| DuckDNS + port forwarding | 0 EUR | Gratuito; sin intermediarios en el tráfico | Dependiente de que el ISP no use CGNAT y no bloquee el puerto |

**Decisión**: DuckDNS + port forwarding en el router doméstico.

- Subdominio: `rpidamh.duckdns.org`
- Script de actualización: `/home/damh/.duckdns/update.sh` (llamada HTTP a la API de DuckDNS)
- Cron en el PC: `*/5 * * * *` cada 5 minutos
- Port forwarding: UDP 51820 (WAN) → 192.168.1.49:51820 (LAN)
- Endpoint del RPi5: `rpidamh.duckdns.org:51820` (antes era la IP física `192.168.1.49`)

**Justificación**: DuckDNS no interviene en el tráfico — solo resuelve un nombre a una IP. El cifrado WireGuard (ChaCha20-Poly1305, Curve25519) opera de extremo a extremo entre el RPi5 y el PC. La seguridad del túnel no depende de DuckDNS; solo la localización del endpoint sí.

**Limitación conocida**: si Movistar activa CGNAT o bloquea el puerto UDP 51820, el port forwarding deja de funcionar. En ese caso, la alternativa es Oracle Free Tier (VPS con IP pública fija) o avanzar a Fase 2 con VPS relay.

---

## DT-007: Sender de doble modo LIVE/BUFFER

**Fecha**: 2026-06-09
**Estado**: Implementado y verificado

**Problema**: El sender original usaba backoff exponencial (hasta 120 s de espera). El tiempo de recuperación tras reconexión podía ser de hasta 2 minutos. Además, enviando datos acumulados durante una caída se retrasaba el stream en vivo.

**Decisión**: Sender con dos modos de operación diferenciados:

- **Modo LIVE**: envía en tiempo real con verificación de SHA-256. Mantiene una ventana deslizante de 10 resultados ACK/NACK. Si los éxitos caen por debajo del umbral (3 de 10), cambia a modo BUFFER.
- **Modo BUFFER**: los segmentos se mueven al directorio de archivo sin intentar transmitirlos. Cada 30 s lanza un ping TCP al servidor. Con 3 pings consecutivos exitosos, vuelve a modo LIVE.

**Ventaja**: el tiempo máximo de recuperación pasa de 120 s (backoff máximo anterior) a 30 s (intervalo de ping). La monitorización en vivo no se interrumpe por datos acumulados: estos se envían de forma separada por el scheduler nocturno.

---

## DT-008: Sincronización nocturna programada

**Fecha**: 2026-06-09
**Estado**: Implementado

**Problema**: Tras una reconexión, enviar horas de segmentos acumulados bloquearía el canal para el stream en vivo.

**Decisión**: Los segmentos acumulados durante caídas de red (en `archive/`) se envían al nodo central una vez al día, a medianoche, mediante un proceso independiente (`sync_scheduler.py`).

**Justificación**: La monitorización de seguridad tiene dos prioridades distintas:
1. Ver lo que ocurre ahora mismo (stream en vivo, crítico).
2. Recuperar lo que ocurrió durante la caída (archivo, puede esperar hasta la noche).

Mezclar ambos en el mismo canal en el mismo momento comprometería la prioridad 1. La sync nocturna se ejecuta cuando la actividad monitoreada es mínima (madrugada).
