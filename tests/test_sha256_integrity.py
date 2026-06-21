#!/usr/bin/env python3
"""
Test de integridad SHA-256 — Nodo Central.

Verifica que el receiver detecta y rechaza correctamente segmentos
con datos manipulados, y que el logger de eventos registra cada incidente.

Escenarios probados (todos en la misma conexión TCP):
  1. Segmento correcto             → ACK  esperado
  2. Hash falso en la cabecera     → NACK esperado (hash_mismatch)
  3. Datos manipulados post-firma  → NACK esperado (hash_mismatch)

Uso:
  python3 tests/test_sha256_integrity.py [--host HOST] [--port PORT]

Ejemplo:
  python3 tests/test_sha256_integrity.py --host 192.168.1.50 --port 9000
"""
import argparse
import hashlib
import json
import socket
import sys
import time
from pathlib import Path

# ── configuración por defecto ─────────────────────────────────────────────────

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9000
CONNECT_TIMEOUT = 5
SEND_TIMEOUT    = 10

LOG_PATH = Path(__file__).parent.parent / "nodo-central" / "logs" / "events.jsonl"


# ── utilidades de protocolo ───────────────────────────────────────────────────

def recv_json(sock: socket.socket) -> dict:
    buf = bytearray()
    while True:
        b = sock.recv(1)
        if not b:
            raise ConnectionError("Conexión cerrada inesperadamente")
        if b == b"\n":
            return json.loads(buf.decode())
        buf.extend(b)


def enviar_segmento(sock: socket.socket, filename: str, data: bytes,
                    sha256_override: str | None = None) -> tuple[bool, dict]:
    """
    Envía un segmento siguiendo el protocolo del sender.

    sha256_override permite enviar un hash incorrecto en la cabecera
    sin modificar los datos, para simular tampering de metadatos.
    Devuelve (exito, respuesta_final_del_receiver).
    """
    file_hash = sha256_override or hashlib.sha256(data).hexdigest()
    header = json.dumps({"filename": filename, "size": len(data), "sha256": file_hash}) + "\n"
    sock.sendall(header.encode())

    resp = recv_json(sock)
    if resp.get("status") != "ok":
        return False, resp

    sock.sendall(data)
    confirm = recv_json(sock)
    return confirm.get("status") == "ok", confirm


def datos_sinteticos(size: int = 4096) -> bytes:
    """Genera datos sintéticos predecibles (no MPEG-TS real, suficiente para el test)."""
    pattern = bytes(range(256))
    return (pattern * (size // 256 + 1))[:size]


# ── lógica del test ───────────────────────────────────────────────────────────

class ResultadoTest:
    def __init__(self, nombre: str, esperado_ok: bool, obtenido_ok: bool, detalle: dict):
        self.nombre      = nombre
        self.esperado_ok = esperado_ok
        self.obtenido_ok = obtenido_ok
        self.detalle     = detalle

    @property
    def paso(self) -> bool:
        return self.esperado_ok == self.obtenido_ok

    @property
    def esperado_str(self) -> str:
        return "ACK" if self.esperado_ok else "NACK"

    @property
    def obtenido_str(self) -> str:
        return "ACK" if self.obtenido_ok else "NACK"


def ejecutar_escenarios(host: str, port: int) -> list[ResultadoTest]:
    """Abre una conexión TCP y ejecuta los tres escenarios en secuencia."""
    try:
        sock = socket.create_connection((host, port), timeout=CONNECT_TIMEOUT)
        sock.settimeout(SEND_TIMEOUT)
    except OSError as e:
        print(f"\n  ERROR: No se puede conectar a {host}:{port} — {e}")
        print("  Asegúrese de que receiver.py está ejecutándose.")
        sys.exit(1)

    resultados = []

    with sock:
        # ── Escenario 1: segmento correcto ──────────────────────────────────
        data_ok = datos_sinteticos(4096)
        ok, resp = enviar_segmento(sock, "test_correcto.ts", data_ok)
        resultados.append(ResultadoTest(
            nombre       = "Segmento con datos y hash correctos",
            esperado_ok  = True,
            obtenido_ok  = ok,
            detalle      = resp,
        ))

        # ── Escenario 2: hash falso en la cabecera (datos íntegros) ─────────
        data_ok2    = datos_sinteticos(4096)
        hash_falso  = "a" * 64   # SHA-256 completamente inventado
        ok, resp = enviar_segmento(sock, "test_hash_falso.ts", data_ok2,
                                   sha256_override=hash_falso)
        resultados.append(ResultadoTest(
            nombre       = "Hash falso en cabecera (metadatos manipulados)",
            esperado_ok  = False,
            obtenido_ok  = ok,
            detalle      = resp,
        ))

        # ── Escenario 3: datos manipulados (hash del original, bytes alterados) ─
        data_original  = datos_sinteticos(4096)
        hash_original  = hashlib.sha256(data_original).hexdigest()
        data_tampered  = bytearray(data_original)
        # Simula un ataque de manipulación bit-flip en dos posiciones
        data_tampered[512]  ^= 0xFF
        data_tampered[1024] ^= 0xAA
        ok, resp = enviar_segmento(sock, "test_datos_manipulados.ts", bytes(data_tampered),
                                   sha256_override=hash_original)
        resultados.append(ResultadoTest(
            nombre       = "Datos manipulados en tránsito (bit-flip post-firma)",
            esperado_ok  = False,
            obtenido_ok  = ok,
            detalle      = resp,
        ))

    return resultados


def contar_eventos_log(filename_parcial: str) -> int:
    """Cuenta cuántos hash_error contiene el log para los archivos de test."""
    if not LOG_PATH.exists():
        return -1
    count = 0
    with open(LOG_PATH) as f:
        for line in f:
            if '"hash_error"' in line and filename_parcial in line:
                count += 1
    return count


# ── salida ────────────────────────────────────────────────────────────────────

SEP = "=" * 62

def imprimir_tabla(resultados: list[ResultadoTest]):
    print(f"\n{'Escenario':<45} {'Esperado':<10} {'Obtenido':<10} {'Resultado'}")
    print("-" * 62)
    for r in resultados:
        resultado_str = "PASS" if r.paso else "FAIL"
        print(f"  {r.nombre:<43} {r.esperado_str:<10} {r.obtenido_str:<10} {resultado_str}")


def main():
    parser = argparse.ArgumentParser(description="Test de integridad SHA-256 del receiver")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()

    print(SEP)
    print("TEST INTEGRIDAD SHA-256")
    print(f"Receiver: {args.host}:{args.port}")
    print(SEP)

    print(f"\nEjecutando {3} escenarios en una única conexión TCP...\n")
    resultados = ejecutar_escenarios(args.host, args.port)

    imprimir_tabla(resultados)

    pasados = sum(1 for r in resultados if r.paso)
    total   = len(resultados)

    print()
    print(SEP)
    print(f"RESULTADO FINAL: {pasados}/{total} escenarios correctos")
    print(SEP)

    if pasados == total:
        print("\nEl receiver detecta correctamente todos los intentos de manipulacion.")
    else:
        for r in resultados:
            if not r.paso:
                print(f"\n  FALLO en '{r.nombre}'")
                print(f"    Detalle: {r.detalle}")

    # Verificar log de eventos
    print("\nVerificando log de eventos del nodo central...")
    time.sleep(0.3)   # margen para que el receiver escriba el log
    errores_en_log = contar_eventos_log("test_")
    if errores_en_log < 0:
        print(f"  AVISO: No se encontró el log en {LOG_PATH}")
    else:
        print(f"  hash_error registrados en events.jsonl: {errores_en_log} (esperado: 2)")
        if errores_en_log == 2:
            print("  Correcto — los intentos de manipulacion quedan auditados.")
        else:
            print("  AVISO: numero de hash_error inesperado.")

    print()
    sys.exit(0 if pasados == total else 1)


if __name__ == "__main__":
    main()
