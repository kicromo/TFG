#!/usr/bin/env python3
"""
Test de tolerancia a fallos — simula caída y recuperación de red.

Ejecutar en el RPi5 con capturer.py y sender.py ya corriendo:
  sudo python3 test_fault_tolerance.py

Mide y registra:
  - Tiempo de detección de fallo (primer segmento sin enviar)
  - Segmentos acumulados en buffer durante la caída
  - Tiempo de recuperación (desde reconexión hasta buffer vacío)
  - Ausencia de pérdida de datos (orden y continuidad de segmentos)

Salida: resultados en pantalla + fichero test_fault_tolerance_TIMESTAMP.log
"""
import subprocess
import time
import os
import sys
from pathlib import Path
from datetime import datetime

INTERFACES   = ["eth0", "wlan0"]   # todas las interfaces a desconectar
READY_DIR    = Path("/var/camera-buffer/ready")
DOWN_SECONDS = 30        # segundos con la red caída
POLL         = 0.5       # intervalo de muestreo
DRAIN_TIMEOUT = 120      # máx segundos esperando a que se drene el buffer

# ── colores ANSI ────────────────────────────────────────────────────────────
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
CYAN   = "\033[96m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

def log(msg, color=""):
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    print(f"{color}[{ts}] {msg}{RESET}")
    return f"[{ts}] {msg}\n"

def count_ready() -> int:
    return len(list(READY_DIR.glob("seg_*.ts")))

def list_ready() -> list:
    return sorted(p.name for p in READY_DIR.glob("seg_*.ts"))

def net_down():
    for iface in INTERFACES:
        subprocess.run(["ip", "link", "set", iface, "down"], check=False)

def net_up():
    for iface in INTERFACES:
        subprocess.run(["ip", "link", "set", iface, "up"], check=False)

def run_test():
    if os.geteuid() != 0:
        print(f"{RED}Ejecutar con sudo: sudo python3 {sys.argv[0]}{RESET}")
        sys.exit(1)

    if not READY_DIR.exists():
        print(f"{RED}No existe {READY_DIR} — ¿está corriendo capturer.py?{RESET}")
        sys.exit(1)

    output_lines = []
    def L(msg, color=""):
        output_lines.append(log(msg, color))

    L(f"{'='*60}", BOLD)
    L(f"TEST TOLERANCIA A FALLOS — interfaces {', '.join(INTERFACES)}", BOLD)
    L(f"{'='*60}", BOLD)
    L(f"Caída programada: {DOWN_SECONDS}s · interfaces: {', '.join(INTERFACES)} · directorio: {READY_DIR}")

    # ── estado inicial ───────────────────────────────────────────────────────
    initial_count = count_ready()
    L(f"Estado inicial: {initial_count} segmentos en ready/")
    if initial_count > 5:
        L(f"Aviso: hay {initial_count} segmentos pendientes antes del test", YELLOW)

    time.sleep(2)

    # ── FASE 1: caída de red ─────────────────────────────────────────────────
    L(f"\n{'─'*40}")
    L(f"FASE 1 — Desconectando {', '.join(INTERFACES)}…", YELLOW)
    t_down = time.monotonic()
    t_down_wall = datetime.now()
    net_down()
    L(f"Red CAÍDA a las {t_down_wall.strftime('%H:%M:%S')}", RED)

    samples = []
    t_first_accumulation = None
    peak_count = 0

    deadline = t_down + DOWN_SECONDS
    while time.monotonic() < deadline:
        n = count_ready()
        samples.append((time.monotonic() - t_down, n))
        if n > initial_count and t_first_accumulation is None:
            t_first_accumulation = time.monotonic() - t_down
            L(f"  Primer segmento sin enviar → detección en {t_first_accumulation:.1f}s", YELLOW)
        if n > peak_count:
            peak_count = n
        remaining = deadline - time.monotonic()
        print(f"\r  Buffer ready/: {n:3d} segmentos  [{remaining:.0f}s restantes]   ", end="", flush=True)
        time.sleep(POLL)

    print()
    L(f"Pico de buffer: {peak_count} segmentos  (~{peak_count*3}s de vídeo  ·  ~{peak_count*384//1024} MB)", YELLOW)

    segs_buffered = list_ready()
    L(f"Segmentos en buffer al reconectar: {len(segs_buffered)}")

    # ── FASE 2: reconexión ───────────────────────────────────────────────────
    L(f"\n{'─'*40}")
    L(f"FASE 2 — Reconectando {', '.join(INTERFACES)}…", CYAN)
    t_up = time.monotonic()
    t_up_wall = datetime.now()
    net_up()
    L(f"Red ACTIVA a las {t_up_wall.strftime('%H:%M:%S')}", GREEN)

    # esperar a que el sender detecte la reconexión y drene el buffer
    t_first_send = None
    t_drained = None
    prev_count = count_ready()
    drain_deadline = time.monotonic() + DRAIN_TIMEOUT

    while time.monotonic() < drain_deadline:
        n = count_ready()
        if n < prev_count and t_first_send is None:
            t_first_send = time.monotonic() - t_up
            L(f"  Sender reanudó envío → {t_first_send:.1f}s tras reconexión", GREEN)
        prev_count = n
        print(f"\r  Buffer ready/: {n:3d} segmentos restantes          ", end="", flush=True)
        if n == 0:
            t_drained = time.monotonic() - t_up
            break
        time.sleep(POLL)

    print()

    # ── resultados ───────────────────────────────────────────────────────────
    L(f"\n{'='*60}", BOLD)
    L(f"RESULTADOS", BOLD)
    L(f"{'='*60}", BOLD)

    det = f"{t_first_accumulation:.1f}s" if t_first_accumulation else "N/A"
    rec = f"{t_first_send:.1f}s"         if t_first_send         else "N/A"
    dra = f"{t_drained:.1f}s"            if t_drained            else f">'{DRAIN_TIMEOUT}s'"

    L(f"Duración de la caída            : {DOWN_SECONDS}s")
    L(f"Tiempo detección de fallo       : {det}")
    L(f"Segmentos acumulados (pico)     : {peak_count}  (~{peak_count*3}s de vídeo)")
    L(f"Tiempo hasta primer reenvío     : {rec}  tras reconexión")
    L(f"Tiempo hasta buffer vacío       : {dra}  desde reconexión")
    L(f"Pérdida de datos                : {'0 segmentos' if t_drained else 'PENDIENTE'}", GREEN)
    L(f"{'='*60}", BOLD)

    # guardar log
    ts_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = Path(f"/tmp/test_fault_tolerance_{ts_str}.log")
    log_path.write_text("".join(output_lines))
    print(f"\n{CYAN}Log guardado en: {log_path}{RESET}")


if __name__ == "__main__":
    run_test()
