#!/usr/bin/env python3
"""
Receiver — Nodo Central (PC / futuro VPS).

Escucha conexiones TCP del Sender (RPi5), recibe segmentos MPEG-TS,
verifica integridad con SHA-256 y los almacena en disco organizado por fecha.

Protocolo (por cada segmento):
  Sender → Receiver : cabecera JSON + '\\n'  { filename, size, sha256 }
  Receiver → Sender : respuesta JSON + '\\n' { status: "ok" | "error", reason? }
  Sender → Receiver : [size bytes de datos raw]
  Receiver → Sender : confirmación JSON + '\\n' { status: "ok" | "error" }
"""
import hashlib
import json
import logging
import os
import signal
import socket
import socketserver
import sys
import threading
from datetime import datetime
from pathlib import Path

import yaml

from event_logger import EventLogger

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).parent / "config.yaml"


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def segment_storage_path(base_dir: Path, filename: str) -> Path:
    """Organiza segmentos en base_dir/YYYY-MM-DD/HH/filename."""
    now = datetime.now()
    day_dir = base_dir / now.strftime("%Y-%m-%d") / now.strftime("%H")
    day_dir.mkdir(parents=True, exist_ok=True)
    return day_dir / filename


def recv_exactly(sock: socket.socket, n: int) -> bytes:
    """Lee exactamente n bytes del socket."""
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(min(65536, n - len(buf)))
        if not chunk:
            raise ConnectionError("Conexión cerrada antes de recibir todos los datos")
        buf.extend(chunk)
    return bytes(buf)


def recv_line(sock: socket.socket) -> str:
    """Lee bytes hasta '\\n' (cabecera JSON)."""
    buf = bytearray()
    while True:
        b = sock.recv(1)
        if not b:
            raise ConnectionError("Conexión cerrada durante lectura de cabecera")
        if b == b"\n":
            return buf.decode()
        buf.extend(b)


def send_json(sock: socket.socket, obj: dict):
    sock.sendall((json.dumps(obj) + "\n").encode())


class SegmentHandler(socketserver.BaseRequestHandler):
    """Maneja una conexión entrante del Sender."""

    def handle(self):
        peer = f"{self.client_address[0]}:{self.client_address[1]}"
        client_ip = self.client_address[0]
        logger.info("Conexión de %s", peer)
        self.server.event_logger.connection_open(peer)

        segments_ok = 0
        segments_error = 0
        try:
            segments_ok, segments_error = self._handle_segments()
        except ConnectionError as e:
            logger.warning("Conexión %s cerrada: %s", peer, e)
        except Exception as e:
            logger.error("Error con %s: %s", peer, e, exc_info=True)
        finally:
            self.server.event_logger.connection_close(peer, segments_ok, segments_error)

    def _handle_segments(self) -> tuple[int, int]:
        base_dir = Path(self.server.config["storage"]["base_dir"])
        ev = self.server.event_logger
        client_ip = self.client_address[0]
        sock = self.request
        ok_count = 0
        err_count = 0

        while True:
            # 1. Recibir cabecera
            try:
                header_line = recv_line(sock)
            except ConnectionError:
                break  # cliente se desconectó limpiamente

            try:
                header = json.loads(header_line)
                filename = header["filename"]
                size = int(header["size"])
                expected_hash = header["sha256"]
            except (json.JSONDecodeError, KeyError) as e:
                reason = f"cabecera inválida: {e}"
                send_json(sock, {"status": "error", "reason": reason})
                ev.header_error(client_ip, reason)
                err_count += 1
                break

            send_json(sock, {"status": "ok"})  # listo para recibir datos

            # 2. Recibir datos del segmento
            data = recv_exactly(sock, size)

            # 3. Verificar integridad
            actual_hash = hashlib.sha256(data).hexdigest()
            if actual_hash != expected_hash:
                logger.warning("Hash incorrecto para %s: esperado %s, recibido %s",
                               filename, expected_hash, actual_hash)
                send_json(sock, {"status": "error", "reason": "hash_mismatch"})
                ev.hash_error(client_ip, filename)
                err_count += 1
                continue

            # 4. Guardar en disco
            dest = segment_storage_path(base_dir, filename)
            dest.write_bytes(data)
            logger.info("Guardado: %s (%d KB)", dest.relative_to(base_dir.parent), size // 1024)
            send_json(sock, {"status": "ok"})
            ev.segment_ok(client_ip, filename, size)
            ok_count += 1

        return ok_count, err_count


class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, server_address, handler_class, config: dict, event_logger: EventLogger):
        self.config = config
        self.event_logger = event_logger
        super().__init__(server_address, handler_class)


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    cfg = load_config()
    host = cfg["server"]["host"]
    port = cfg["server"]["port"]

    Path(cfg["storage"]["base_dir"]).mkdir(parents=True, exist_ok=True)

    ev = EventLogger(
        log_dir      = Path(cfg["logs"]["dir"]),
        max_bytes    = cfg["logs"]["max_bytes"],
        backup_count = cfg["logs"]["backup_count"],
    )

    server = ThreadedTCPServer((host, port), SegmentHandler, cfg, ev)

    def _stop(sig, frame):
        logger.info("Deteniendo receiver…")
        threading.Thread(target=server.shutdown).start()

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    logger.info("Receiver escuchando en %s:%d", host, port)
    server.serve_forever()


if __name__ == "__main__":
    main()
