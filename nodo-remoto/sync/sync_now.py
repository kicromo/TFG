#!/usr/bin/env python3
"""
Lanza la sync de archivo manualmente, sin esperar a la hora programada.

Uso:
    python3 nodo-remoto/sync/sync_now.py          # desde la raíz del repo
    ./nodo-remoto/sync/sync_now.py                # con permisos de ejecución
"""
import logging
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))
from sync_scheduler import run_sync

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

CONFIG_PATH = Path(__file__).parent.parent / "config" / "config.yaml"

with open(CONFIG_PATH) as f:
    cfg = yaml.safe_load(f)

host        = cfg["server"]["host"]
port        = cfg["server"]["port"]
archive_dir = Path(cfg["sync"]["archive_dir"])
syncing_dir = archive_dir.parent / "syncing"

syncing_dir.mkdir(parents=True, exist_ok=True)

logging.getLogger(__name__).info(
    "Sync manual — %d segmento(s) en archive",
    len(list(archive_dir.glob("seg_*.ts"))),
)

run_sync(host, port, archive_dir, syncing_dir)
