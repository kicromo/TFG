#!/bin/bash
# Ejecutar en la RPi5 para ver capacidades de la WebCam
# Uso: bash probe-webcam.sh

set -e

echo "=== Dispositivos de vídeo disponibles ==="
ls /dev/video* 2>/dev/null || echo "No se encontraron dispositivos /dev/video*"

echo ""
echo "=== Información del sistema ==="
uname -a
cat /proc/cpuinfo | grep "Model" | head -1

echo ""
echo "=== Memoria disponible ==="
free -h

echo ""
echo "=== Formatos y resoluciones soportadas (v4l2-ctl) ==="
for dev in /dev/video*; do
    echo "--- Dispositivo: $dev ---"
    v4l2-ctl --device="$dev" --list-formats-ext 2>/dev/null || echo "No es un dispositivo de captura o falta v4l2-ctl"
    echo ""
done

echo ""
echo "=== Controles disponibles en /dev/video0 ==="
v4l2-ctl --device=/dev/video0 --list-ctrls 2>/dev/null || true

echo ""
echo "=== Aceleración hardware (codecs disponibles) ==="
ffmpeg -hide_banner -encoders 2>/dev/null | grep -E "264|265|hevc|v4l2" || echo "FFmpeg no instalado"

echo ""
echo "=== Test de captura: 3 segundos a 720p ==="
echo "Capturando 3 seg de /dev/video0 → /tmp/test_capture.ts ..."
ffmpeg -hide_banner -loglevel warning \
    -f v4l2 -input_format yuyv422 -video_size 1280x720 -framerate 15 \
    -i /dev/video0 \
    -c:v h264_v4l2m2m -b:v 1000k \
    -t 3 -f mpegts /tmp/test_capture.ts && \
    echo "OK — archivo: $(du -h /tmp/test_capture.ts | cut -f1)" || \
    echo "Fallo con h264_v4l2m2m, intentando libx264 (software)..." && \
    ffmpeg -hide_banner -loglevel warning \
        -f v4l2 -input_format yuyv422 -video_size 1280x720 -framerate 15 \
        -i /dev/video0 \
        -c:v libx264 -preset ultrafast -b:v 1000k \
        -t 3 -f mpegts /tmp/test_capture.ts && \
    echo "OK (software) — archivo: $(du -h /tmp/test_capture.ts | cut -f1)"

echo ""
echo "=== Resumen de uso de CPU durante captura ==="
top -bn1 | grep -E "Cpu|cpu" | head -3
