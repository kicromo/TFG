#!/usr/bin/env python3
"""
Captura vídeo de la WebCam y produce segmentos MPEG-TS de duración fija.

Flujo:
  FFmpeg → staging/seg_YYYYMMDD_HHMMSS.ts (en escritura)
         → ready/seg_YYYYMMDD_HHMMSS.ts   (completo, listo para enviar)

El traspaso de staging a ready ocurre cuando FFmpeg ya ha empezado a escribir
el siguiente segmento, garantizando que el anterior está cerrado y completo.
"""
import subprocess
import time
import shutil
import logging
import signal
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def build_ffmpeg_cmd(cfg: dict, staging_dir: Path) -> list:
    cam = cfg["camera"]
    seg_duration = cfg["capture"]["segment_duration"]
    pattern = str(staging_dir / "seg_%Y%m%d_%H%M%S.ts")

    return [
        "ffmpeg", "-hide_banner", "-loglevel", "warning",
        # Entrada
        "-f", "v4l2",
        "-input_format", cam["format"],
        "-video_size", cam["resolution"],
        "-framerate", str(cam["framerate"]),
        "-i", cam["device"],
        # Codificación
        "-c:v", cam["codec"],
        "-preset", cam["preset"],
        "-tune", "zerolatency",
        "-b:v", cam["bitrate"],
        # Forzar keyframe al inicio de cada segmento (necesario para corte exacto)
        "-g", str(cam["framerate"] * seg_duration),
        "-keyint_min", str(cam["framerate"] * seg_duration),
        # Segmentación
        "-f", "segment",
        "-segment_time", str(seg_duration),
        "-segment_format", "mpegts",
        "-reset_timestamps", "1",
        "-strftime", "1",
        pattern,
    ]


class Capturer:
    """
    Lanza FFmpeg y mueve cada segmento terminado a ready/ para que el Sender
    lo recoja. Se detiene limpiamente con stop() o con SIGINT/SIGTERM.
    """

    POLL_INTERVAL = 0.5  # segundos entre comprobaciones del directorio

    def __init__(self, cfg: dict):
        self.cfg = cfg
        buffer_dir = Path(cfg["capture"]["buffer_dir"])
        self.staging_dir = buffer_dir / "staging"
        self.ready_dir = buffer_dir / "ready"
        self.staging_dir.mkdir(parents=True, exist_ok=True)
        self.ready_dir.mkdir(parents=True, exist_ok=True)
        self._proc: subprocess.Popen | None = None
        self._running = False

    # ------------------------------------------------------------------ #
    #  Ciclo principal                                                     #
    # ------------------------------------------------------------------ #

    def start(self):
        self._running = True
        cmd = build_ffmpeg_cmd(self.cfg, self.staging_dir)
        logger.info("Iniciando FFmpeg: %s", " ".join(cmd))

        self._proc = subprocess.Popen(cmd, stderr=subprocess.PIPE)
        logger.info("FFmpeg PID %d arrancado", self._proc.pid)

        try:
            self._watch_segments()
        finally:
            self._flush_remaining()

    def stop(self):
        logger.info("Deteniendo capturer…")
        self._running = False
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()

    # ------------------------------------------------------------------ #
    #  Lógica interna                                                      #
    # ------------------------------------------------------------------ #

    def _watch_segments(self):
        """
        Comprueba periódicamente el directorio staging.
        Si hay más de un archivo .ts, todos menos el último están completos
        (FFmpeg ya los cerró al abrir el siguiente).
        """
        promoted: set = set()

        while self._running and self._proc.poll() is None:
            segments = sorted(self.staging_dir.glob("seg_*.ts"))
            completed = segments[:-1]  # el último sigue en escritura

            for seg in completed:
                if seg.name not in promoted:
                    self._promote(seg)
                    promoted.add(seg.name)

            time.sleep(self.POLL_INTERVAL)

        # FFmpeg terminó (error o stop()) — comprobar stderr
        if self._proc.returncode not in (0, -15):  # -15 = SIGTERM normal
            err = self._proc.stderr.read().decode(errors="replace") if self._proc.stderr else ""
            if err:
                logger.error("FFmpeg error:\n%s", err)

    def _promote(self, seg: Path):
        """Mueve un segmento terminado de staging/ a ready/."""
        dest = self.ready_dir / seg.name
        shutil.move(str(seg), str(dest))
        size_kb = dest.stat().st_size // 1024
        logger.info("Segmento listo: %s (%d KB)", dest.name, size_kb)

    def _flush_remaining(self):
        """Al salir, mueve cualquier segmento que haya quedado en staging."""
        for seg in sorted(self.staging_dir.glob("seg_*.ts")):
            if seg.stat().st_size > 0:
                self._promote(seg)


# ------------------------------------------------------------------ #
#  Ejecución directa (para pruebas)                                    #
# ------------------------------------------------------------------ #

if __name__ == "__main__":
    import yaml

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    config_path = Path(__file__).parent.parent / "config" / "config.yaml"
    with open(config_path) as f:
        config = yaml.safe_load(f)

    capturer = Capturer(config)

    def _handle_signal(sig, frame):
        capturer.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    capturer.start()
