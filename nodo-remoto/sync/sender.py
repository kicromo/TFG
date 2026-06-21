#!/usr/bin/env python3
"""
Sender — Nodo Remoto (RPi5).

Modos de operación
──────────────────
LIVE  : envía segmentos en tiempo real al servidor con verificación SHA-256.
        Registra cada ACK/NACK en una ventana deslizante (ConnectionHealth).
        Si los éxitos caen por debajo del umbral → cambia a modo BUFFER.

BUFFER: la red es demasiado inestable para streaming en vivo.
        Los segmentos se mueven a archive_dir para la sync programada nocturna.
        Cada ping_interval segundos comprueba si el servidor vuelve a responder.
        Si recovery_pings pings consecutivos tienen éxito → vuelve a LIVE.

Protocolo por segmento (modo LIVE):
  Sender → Receiver : cabecera JSON + '\\n'  { filename, size, sha256 }
  Receiver → Sender : { status: "ok" }  ←  ACK
                    : { status: "error", reason: "..." }  ←  NACK
  Sender → Receiver : [size bytes de datos raw]
  Receiver → Sender : { status: "ok" }  ←  confirmación de almacenamiento
"""
import hashlib
import json
import logging
import shutil
import signal
import socket
import sys
import time
from collections import deque
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).parent.parent / "config" / "config.yaml"

CONNECT_TIMEOUT = 5
SEND_TIMEOUT    = 30
POLL_INTERVAL   = 1   # segundos entre comprobaciones de ready/


# ── utilidades de red ────────────────────────────────────────────────────────

def recv_json(sock: socket.socket) -> dict:
    buf = bytearray()
    while True:
        b = sock.recv(1)
        if not b:
            raise ConnectionError("Conexión cerrada inesperadamente")
        if b == b"\n":
            return json.loads(buf.decode())
        buf.extend(b)


def send_segment(sock: socket.socket, seg: Path) -> bool:
    """
    Envía un segmento y devuelve True si el servidor confirma recepción correcta.
    """
    data      = seg.read_bytes()
    file_hash = hashlib.sha256(data).hexdigest()

    header = json.dumps({"filename": seg.name, "size": len(data), "sha256": file_hash}) + "\n"
    sock.sendall(header.encode())

    resp = recv_json(sock)
    if resp.get("status") != "ok":
        logger.warning("Servidor rechazó cabecera de %s: %s", seg.name, resp)
        return False

    sock.sendall(data)

    confirm = recv_json(sock)
    if confirm.get("status") == "ok":
        return True

    logger.warning("Servidor rechazó segmento %s: %s", seg.name, confirm.get("reason"))
    return False


def tcp_ping(host: str, port: int) -> bool:
    """Comprobación ligera de conectividad: solo intenta abrir la conexión TCP."""
    try:
        with socket.create_connection((host, port), timeout=CONNECT_TIMEOUT):
            return True
    except OSError:
        return False


# ── health tracker ───────────────────────────────────────────────────────────

class ConnectionHealth:
    """
    Ventana deslizante de ACK/NACK para decidir el modo de operación.

    LIVE  → BUFFER : éxitos en ventana < live_threshold
    BUFFER → LIVE  : recovery_pings pings TCP consecutivos con éxito
    """

    def __init__(self, window_size: int, live_threshold: int, recovery_pings: int):
        self.window            = deque(maxlen=window_size)
        self.live_threshold    = live_threshold
        self.recovery_pings    = recovery_pings
        self._consecutive_pings = 0
        self.mode              = "LIVE"

    def record(self, success: bool):
        """Registra el resultado de un envío en modo LIVE."""
        self.window.append(success)
        successes = sum(self.window)
        if self.mode == "LIVE" and len(self.window) == self.window.maxlen:
            if successes < self.live_threshold:
                self.mode = "BUFFER"
                logger.warning(
                    "Salud de red baja (%d/%d OK) → cambiando a modo BUFFER",
                    successes, len(self.window)
                )

    def record_ping(self, success: bool):
        """Registra el resultado de un ping en modo BUFFER."""
        if success:
            self._consecutive_pings += 1
            if self._consecutive_pings >= self.recovery_pings:
                self.mode = "LIVE"
                self.window.clear()
                self._consecutive_pings = 0
                logger.info("Red recuperada (%d pings OK) → cambiando a modo LIVE", self.recovery_pings)
        else:
            self._consecutive_pings = 0

    @property
    def is_live(self) -> bool:
        return self.mode == "LIVE"

    def summary(self) -> str:
        s = sum(self.window)
        return f"{s}/{len(self.window)} ACK — modo {self.mode}"


# ── sender principal ─────────────────────────────────────────────────────────

class Sender:

    def __init__(self, cfg: dict):
        self.host        = cfg["server"]["host"]
        self.port        = cfg["server"]["port"]
        self.ready_dir   = Path(cfg["capture"]["buffer_dir"]) / "ready"
        self.archive_dir = Path(cfg["sync"]["archive_dir"])
        self.ping_interval = cfg["health"]["ping_interval"]

        self.archive_dir.mkdir(parents=True, exist_ok=True)

        self.health = ConnectionHealth(
            window_size    = cfg["health"]["window_size"],
            live_threshold = cfg["health"]["live_threshold"],
            recovery_pings = cfg["health"]["recovery_pings"],
        )
        self._running = False

    def start(self):
        self._running = True
        logger.info("Sender iniciado → %s:%d", self.host, self.port)
        self._loop()

    def stop(self):
        self._running = False

    # ── bucle principal ──────────────────────────────────────────────────────

    def _loop(self):
        last_ping = 0.0

        while self._running:
            segments = self._pending_segments()

            if self.health.is_live:
                self._run_live(segments)
            else:
                self._run_buffer(segments)
                # comprobar recuperación periódicamente
                now = time.monotonic()
                if now - last_ping >= self.ping_interval:
                    last_ping = now
                    ok = tcp_ping(self.host, self.port)
                    self.health.record_ping(ok)
                    logger.info(
                        "Ping %s → %s | %s",
                        f"{self.host}:{self.port}",
                        "OK" if ok else "FAIL",
                        self.health.summary(),
                    )

            time.sleep(POLL_INTERVAL)

    # ── modo LIVE ────────────────────────────────────────────────────────────

    def _run_live(self, segments: list[Path]):
        if not segments:
            return

        try:
            sock = socket.create_connection((self.host, self.port), timeout=CONNECT_TIMEOUT)
            sock.settimeout(SEND_TIMEOUT)
        except OSError as e:
            logger.warning("Sin conexión al servidor (%s) | %s", e, self.health.summary())
            for seg in segments:
                self.health.record(False)
            # Si la ventana ya decide BUFFER, los moverá en la próxima iteración
            return

        logger.info("Conectado — %d segmento(s) | %s", len(segments), self.health.summary())

        try:
            with sock:
                for seg in segments:
                    if not self._running:
                        break
                    logger.info("Enviando %s (%d KB)…", seg.name, seg.stat().st_size // 1024)
                    success = send_segment(sock, seg)
                    self.health.record(success)

                    if success:
                        seg.unlink()
                        logger.info("ACK ✓ %s | %s", seg.name, self.health.summary())
                    else:
                        # NACK → archivar para sync nocturna
                        self._archive(seg)
                        logger.warning("NACK ✗ %s → archivado | %s", seg.name, self.health.summary())

                    if not self.health.is_live:
                        logger.warning("Umbral de salud alcanzado → resto de segmentos al archivo")
                        break

        except OSError as e:
            logger.warning("Error de red durante envío: %s | %s", e, self.health.summary())
            for seg in segments:
                self.health.record(False)

    # ── modo BUFFER ──────────────────────────────────────────────────────────

    def _run_buffer(self, segments: list[Path]):
        for seg in segments:
            self._archive(seg)
            logger.debug("BUFFER %s → archivado", seg.name)
        if segments:
            logger.info("Modo BUFFER: %d segmento(s) archivado(s) para sync nocturna", len(segments))

    # ── utilidades ───────────────────────────────────────────────────────────

    def _pending_segments(self) -> list[Path]:
        return sorted(self.ready_dir.glob("seg_*.ts"))

    def _archive(self, seg: Path):
        dest = self.archive_dir / seg.name
        shutil.move(str(seg), str(dest))


# ── entrada ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    with open(CONFIG_PATH) as f:
        cfg = yaml.safe_load(f)

    sender = Sender(cfg)

    def _stop(sig, frame):
        sender.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    sender.start()
