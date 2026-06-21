#!/usr/bin/env python3
"""
EventLogger — registro estructurado de eventos del nodo central.

Escribe en formato JSON Lines (un objeto JSON por línea) con rotación
automática del fichero. Los logs pueden consultarse con grep o jq.

Tipos de evento registrados:
  connection_open   — nueva conexión entrante del sender/scheduler
  connection_close  — conexión cerrada (resumen de segmentos procesados)
  segment_ok        — segmento recibido, hash verificado y guardado en disco
  hash_error        — hash SHA-256 no coincide (evento de seguridad)
  header_error      — cabecera JSON inválida o malformada

Ejemplo de línea en events.jsonl:
  {"ts":"2026-06-21T22:05:01.123","event":"segment_ok","client":"192.168.1.38","file":"seg_20260621_220501.ts","size_kb":384.0}
"""
import json
import logging
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path


class EventLogger:

    def __init__(self, log_dir: Path, max_bytes: int = 10_485_760, backup_count: int = 7):
        log_dir.mkdir(parents=True, exist_ok=True)

        handler = RotatingFileHandler(
            log_dir / "events.jsonl",
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter("%(message)s"))

        self._log = logging.getLogger("events")
        self._log.setLevel(logging.DEBUG)
        self._log.propagate = False
        self._log.addHandler(handler)

    def _emit(self, event: str, **kwargs):
        record = {
            "ts": datetime.now().isoformat(timespec="milliseconds"),
            "event": event,
            **kwargs,
        }
        self._log.info(json.dumps(record, ensure_ascii=False))

    def connection_open(self, client: str):
        self._emit("connection_open", client=client)

    def connection_close(self, client: str, segments_ok: int, segments_error: int):
        self._emit(
            "connection_close",
            client=client,
            segments_ok=segments_ok,
            segments_error=segments_error,
        )

    def segment_ok(self, client: str, filename: str, size_bytes: int):
        self._emit(
            "segment_ok",
            client=client,
            file=filename,
            size_kb=round(size_bytes / 1024, 1),
        )

    def hash_error(self, client: str, filename: str):
        self._emit("hash_error", client=client, file=filename)

    def header_error(self, client: str, reason: str):
        self._emit("header_error", client=client, reason=reason)
