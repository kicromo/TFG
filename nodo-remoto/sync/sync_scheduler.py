#!/usr/bin/env python3
"""
Sync Scheduler — Nodo Remoto (RPi5).

Envía al nodo central los segmentos acumulados en archive_dir durante
caídas de red, a la hora programada (por defecto medianoche).

Flujo por ejecución:
  1. Mueve todos los .ts de archive_dir/ → syncing/ (atómico, evita
     conflictos con el sender que también escribe en archive_dir).
  2. Abre una conexión TCP al receiver y envía cada segmento con el
     mismo protocolo que sender.py (cabecera JSON → ACK → datos → confirm).
  3. ACK  → elimina el segmento de syncing/.
  4. NACK → devuelve el segmento a archive_dir/ para la noche siguiente.
  5. Error de red → devuelve todos los pendientes a archive_dir/.
  6. Registra un resumen y espera hasta la próxima ejecución.

Protocolo por segmento (igual que sender.py):
  Scheduler → Receiver : { filename, size, sha256 } + '\\n'
  Receiver → Scheduler : { status: "ok" | "error" }
  Scheduler → Receiver : [size bytes raw]
  Receiver → Scheduler : { status: "ok" | "error" }
"""
import hashlib
import json
import logging
import shutil
import signal
import socket
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).parent.parent / "config" / "config.yaml"

CONNECT_TIMEOUT = 10
SEND_TIMEOUT    = 60   # segmentos en sync no requieren baja latencia


# ── utilidades de red (mismo protocolo que sender.py) ────────────────────────

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
    """Envía un segmento y devuelve True si el receiver confirma recepción correcta."""
    data      = seg.read_bytes()
    file_hash = hashlib.sha256(data).hexdigest()

    header = json.dumps({"filename": seg.name, "size": len(data), "sha256": file_hash}) + "\n"
    sock.sendall(header.encode())

    resp = recv_json(sock)
    if resp.get("status") != "ok":
        logger.warning("Receiver rechazó cabecera de %s: %s", seg.name, resp)
        return False

    sock.sendall(data)

    confirm = recv_json(sock)
    if confirm.get("status") == "ok":
        return True

    logger.warning("Receiver rechazó segmento %s: %s", seg.name, confirm.get("reason"))
    return False


# ── lógica de sync ────────────────────────────────────────────────────────────

def seconds_until_next_run(hour: int, minute: int) -> float:
    """Segundos hasta la próxima ocurrencia de hour:minute (puede ser hoy o mañana)."""
    now    = datetime.now()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


def run_sync(host: str, port: int, archive_dir: Path, syncing_dir: Path):
    """Ejecuta un ciclo completo de sync nocturna."""
    segments = sorted(archive_dir.glob("seg_*.ts"))
    if not segments:
        logger.info("Sync nocturna: archive vacío — nada que enviar")
        return

    # 1. Mover a syncing/ de forma atómica antes de abrir la conexión
    for seg in segments:
        shutil.move(str(seg), str(syncing_dir / seg.name))

    to_send      = sorted(syncing_dir.glob("seg_*.ts"))
    total        = len(to_send)
    total_mb     = sum(s.stat().st_size for s in to_send) / 1_048_576
    logger.info("=== SYNC NOCTURNA INICIO === %d segmento(s) — %.1f MB", total, total_mb)

    sent       = 0
    failed     = 0
    bytes_sent = 0

    # 2. Conectar al receiver
    try:
        sock = socket.create_connection((host, port), timeout=CONNECT_TIMEOUT)
        sock.settimeout(SEND_TIMEOUT)
    except OSError as e:
        logger.error("Sin conexión al servidor (%s) — sync cancelada", e)
        _return_all(to_send, archive_dir)
        logger.warning("%d segmento(s) devueltos a archive_dir para mañana", total)
        return

    # 3. Enviar cada segmento
    with sock:
        for seg in to_send:
            if not seg.exists():
                continue
            seg_size = seg.stat().st_size
            try:
                logger.info("Sync: %s (%d KB)…", seg.name, seg_size // 1024)
                ok = send_segment(sock, seg)
                if ok:
                    bytes_sent += seg_size
                    seg.unlink()
                    sent += 1
                    logger.info("Sync ACK ✓  %s  [%d/%d]", seg.name, sent, total)
                else:
                    shutil.move(str(seg), str(archive_dir / seg.name))
                    failed += 1
                    logger.warning("Sync NACK ✗  %s → archive_dir", seg.name)
            except OSError as e:
                logger.warning("Error de red durante envío de %s: %s", seg.name, e)
                shutil.move(str(seg), str(archive_dir / seg.name))
                failed += 1
                # Conexión rota — mover restantes y abortar
                remaining = [s for s in to_send if s.exists()]
                _return_all(remaining, archive_dir)
                failed += len(remaining)
                logger.warning("Conexión perdida — %d segmento(s) adicionales devueltos a archive_dir",
                               len(remaining))
                break

    # Resumen
    logger.info(
        "=== SYNC NOCTURNA FIN === enviados: %d/%d  |  fallidos: %d  |  %.1f MB transferidos",
        sent, total, failed, bytes_sent / 1_048_576,
    )


def _return_all(segs: list[Path], dest: Path):
    """Devuelve una lista de segmentos al directorio de archive."""
    for seg in segs:
        if seg.exists():
            shutil.move(str(seg), str(dest / seg.name))


# ── bucle principal ───────────────────────────────────────────────────────────

def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    with open(CONFIG_PATH) as f:
        cfg = yaml.safe_load(f)

    host        = cfg["server"]["host"]
    port        = cfg["server"]["port"]
    archive_dir = Path(cfg["sync"]["archive_dir"])
    syncing_dir = archive_dir.parent / "syncing"
    hour        = cfg["sync"]["scheduled_hour"]
    minute      = cfg["sync"]["scheduled_minute"]

    archive_dir.mkdir(parents=True, exist_ok=True)
    syncing_dir.mkdir(parents=True, exist_ok=True)

    # Si quedaron segmentos de una sync interrumpida, recuperarlos
    leftover = list(syncing_dir.glob("seg_*.ts"))
    if leftover:
        logger.warning("Recuperando %d segmento(s) de sync interrumpida → archive_dir", len(leftover))
        _return_all(leftover, archive_dir)

    running = True

    def _stop(sig, frame):
        nonlocal running
        running = False
        sys.exit(0)

    signal.signal(signal.SIGINT,  _stop)
    signal.signal(signal.SIGTERM, _stop)

    logger.info("Sync scheduler iniciado — ejecución diaria a %02d:%02d", hour, minute)

    while running:
        wait    = seconds_until_next_run(hour, minute)
        next_dt = datetime.now() + timedelta(seconds=wait)
        logger.info("Próxima sync: %s (en %.0f min)", next_dt.strftime("%Y-%m-%d %H:%M"), wait / 60)

        # Dormir en intervalos de 60s para poder responder a señales
        slept = 0.0
        while slept < wait and running:
            chunk  = min(60.0, wait - slept)
            time.sleep(chunk)
            slept += chunk

        if running:
            run_sync(host, port, archive_dir, syncing_dir)


if __name__ == "__main__":
    main()
