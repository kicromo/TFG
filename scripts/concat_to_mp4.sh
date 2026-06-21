#!/usr/bin/env bash
# concat_to_mp4.sh — concatena segmentos .ts de una fecha/hora en un único .mp4
#
# Uso:
#   ./concat_to_mp4.sh YYYY-MM-DD [HH] [output.mp4]
#
# Ejemplos:
#   ./concat_to_mp4.sh 2026-06-20           → todo el día, output: 2026-06-20.mp4
#   ./concat_to_mp4.sh 2026-06-20 14        → solo la hora 14, output: 2026-06-20_14.mp4
#   ./concat_to_mp4.sh 2026-06-20 14 out.mp4 → nombre personalizado

set -euo pipefail

STORAGE_DIR="$(realpath "$(dirname "$0")/../nodo-central/storage/video")"
DATE="${1:-}"
HOUR="${2:-}"
OUTPUT="${3:-}"

if [[ -z "$DATE" ]]; then
    echo "Uso: $0 YYYY-MM-DD [HH] [output.mp4]" >&2
    exit 1
fi

# Directorio fuente
if [[ -n "$HOUR" ]]; then
    SRC_DIR="$STORAGE_DIR/$DATE/$(printf '%02d' "$HOUR")"
    OUTPUT="${OUTPUT:-${DATE}_$(printf '%02d' "$HOUR").mp4}"
else
    SRC_DIR="$STORAGE_DIR/$DATE"
    OUTPUT="${OUTPUT:-${DATE}.mp4}"
fi

if [[ ! -d "$SRC_DIR" ]]; then
    echo "Error: directorio no encontrado: $SRC_DIR" >&2
    exit 1
fi

# Construir lista de segmentos ordenada
CONCAT_LIST=$(mktemp /tmp/concat_XXXXXX.txt)
trap 'rm -f "$CONCAT_LIST"' EXIT

find "$SRC_DIR" -name "seg_*.ts" | sort | while read -r f; do
    echo "file '$f'"
done > "$CONCAT_LIST"

COUNT=$(wc -l < "$CONCAT_LIST")
if [[ "$COUNT" -eq 0 ]]; then
    echo "No se encontraron segmentos .ts en $SRC_DIR" >&2
    exit 1
fi

DURATION_S=$(( COUNT * 3 ))
echo "Concatenando $COUNT segmentos (~${DURATION_S}s de vídeo) → $OUTPUT"

ffmpeg -hide_banner -loglevel warning \
    -f concat -safe 0 -i "$CONCAT_LIST" \
    -c copy \
    "$OUTPUT"

SIZE=$(du -h "$OUTPUT" | cut -f1)
echo "OK — $OUTPUT  ($SIZE)"
