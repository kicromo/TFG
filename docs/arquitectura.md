# Arquitectura del Sistema

## Visión general

Sistema IoT distribuido geográficamente (Bolivia → España) para transmisión de vídeo segura y tolerante a fallos. El nodo remoto (RPi5) captura vídeo continuo, lo segmenta y lo transmite al nodo central (PC/VPS) a través de un canal cifrado con VPN WireGuard. El sistema garantiza cero pérdida de grabación incluso ante desconexiones prolongadas.

Ver diagrama: [arquitectura.mmd](diagrams/arquitectura.mmd)

---

## Decisiones de diseño

### 1. Protocolo de red — WireGuard VPN

**Problema**: RPi5 en Bolivia y PC en España están detrás de NAT distintos, en redes no controladas. No se puede abrir puertos directamente.

**Opciones evaluadas**:

| Protocolo | Ventajas | Desventajas |
|-----------|----------|-------------|
| WireGuard (adoptado) | Kernel-level, ChaCha20, baja CPU, NAT traversal | Requiere IP pública en un extremo |
| MQTT + TLS | Bueno para IoT, broker en medio | No ideal para vídeo, añade broker extra |
| WebRTC | P2P, NAT traversal built-in | Complejo, orientado a navegadores |
| RTMP | Push nativo en FFmpeg | Sin cifrado nativo, necesita servidor público |
| TCP directo | Simple | Imposible sin IP pública o reenvío de puertos |
| Tailscale | Zero-config, basado en WireGuard | Dependencia de terceros (coordinación en sus servidores) |

**Decisión**: WireGuard auto-gestionado.
- Durante el desarrollo: PC actúa como servidor WireGuard con puerto UDP abierto en el router.
- En producción: VPS en España con IP pública actúa como endpoint WireGuard. RPi5 y PC se conectan a él.

---

### 2. Transporte de vídeo — Segmentos HLS-like sobre VPN

**Problema**: La transmisión debe resistir desconexiones (la conexión en Bolivia puede ser inestable).

**Opciones evaluadas**:

| Método | Latencia | Tolerancia a fallos | Complejidad |
|--------|----------|---------------------|-------------|
| Segmentos MPEG-TS (adoptado) | 3–8 seg | Alta (cada segmento es atómico) | Media |
| RTSP continuo | Menor de 1 seg | Baja (pierde todo al cortar) | Media |
| RTMP push | ~2 seg | Baja (necesita reconexión manual) | Baja |

**Decisión**: Segmentos de 3 segundos (`.ts` MPEG-TS) generados por FFmpeg.
- Cada segmento es un archivo independiente: se puede bufferizar, reintentar y verificar con hash.
- Compatible con reproductores HLS en el futuro (VLC, navegador con hls.js).
- Integración natural con el buffer local: si no hay red, el segmento se guarda en disco.

**Flujo de un segmento**:
```
FFmpeg captura → segmento.ts → SHA-256 hash → envío TCP sobre VPN
                                   |
                              (si falla red)
                                   |
                          buffer local /var/camera-buffer/
                                   |
                          (al reconectar o a medianoche)
                                   |
                          sync diferida → servidor
```

---

### 3. Codificación de vídeo

**Hardware**: RPi5 tiene VideoCore VII. En la práctica, `h264_v4l2m2m` no expone un encoder H.264 accesible por FFmpeg (ver DT-003). Se usa codificación software.

| Codec | CPU RPi5 | Calidad | Compatibilidad |
|-------|----------|---------|----------------|
| H.264 libx264 (adoptado) | ~6% total (ultrafast) | Buena | Universal |
| H.265/HEVC | Software alto | Mejor | Menos soporte en navegadores |
| VP8/VP9 | Solo software (alto) | Buena | Solo navegadores |

**Decisión**: H.264 con `libx264 -preset ultrafast -tune zerolatency`.
- Resolución: 720p a 15 fps (equilibrio calidad/ancho de banda/CPU).
- Bitrate objetivo: 1 Mbps CBR.

---

### 4. Seguridad

| Capa | Mecanismo |
|------|-----------|
| Canal | WireGuard (ChaCha20-Poly1305, autenticación por clave pública) |
| Autenticación API | JWT con expiración corta |
| Contraseñas locales | bcrypt (cost factor mayor o igual a 12) |
| Integridad de segmentos | SHA-256 por segmento, verificado en recepción |
| Registro de eventos | Log inmutable en JSON Lines con timestamp |
| Control de acceso | Credenciales cifradas en nodo central |

---

## Estructura del proyecto

```
TFG/
├── docs/
│   ├── arquitectura.md
│   ├── decisiones-tecnicas.md
│   ├── diagrams/
│   └── sesiones/
├── nodo-remoto/                 (código para RPi5)
│   ├── capture/capturer.py
│   ├── sync/sender.py
│   ├── sync/sync_scheduler.py
│   └── config/config.yaml
├── nodo-central/                (código para PC/VPS España)
│   ├── receiver/receiver.py
│   ├── receiver/event_logger.py
│   ├── receiver/config.yaml
│   ├── storage/
│   └── logs/
├── scripts/
│   └── concat_to_mp4.sh
└── tests/
    └── test_fault_tolerance.py
```

---

## Fases de despliegue

El sistema se implementa en tres fases de red progresivas. La lógica de captura, buffer y sincronización es idéntica en todas. Solo cambia la capa de transporte de red.

| Fase | Escenario | Red | Estado |
|------|-----------|-----|--------|
| 0 | RPi5 y PC en la misma LAN (España) | TCP directo LAN | Completado |
| 1 | Redes distintas dentro de España | WireGuard VPN | Siguiente paso |
| 2 | Internacional (cualquier país hacia España) | WireGuard VPN con VPS | Objetivo final |

El `Sender` del RPi5 solo conoce `(host, port)` leído del archivo de configuración. Cambiar de LAN a WireGuard es cambiar esa IP en `config.yaml`, sin tocar el código de la aplicación.
