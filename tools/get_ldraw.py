"""Descarga la biblioteca de piezas LDraw (unos 147 MB) en ./ldraw. Solo hace falta para generar diseños nuevos.

Uso:  python tools/get_ldraw.py
"""
import sys
import urllib.request
import zipfile
from pathlib import Path

URL = "https://library.ldraw.org/library/updates/complete.zip"
ROOT = Path(__file__).resolve().parent.parent
ZIP = ROOT / "ldraw_complete.zip"

if (ROOT / "ldraw" / "parts").is_dir():
    print("La biblioteca LDraw ya está en", ROOT / "ldraw")
    sys.exit(0)

print("Descargando LDraw (~147 MB)...")


def progress(blocks, size, total):
    if total > 0:
        done = min(blocks * size, total)
        print(f"\r  {done / 1e6:6.1f} / {total / 1e6:.1f} MB", end="", flush=True)


urllib.request.urlretrieve(URL, ZIP, progress)
print("\nDescomprimiendo...")
with zipfile.ZipFile(ZIP) as z:
    z.extractall(ROOT)
ZIP.unlink()
if not (ROOT / "ldraw" / "parts").is_dir():
    sys.exit("No encontré ldraw/parts después de descomprimir.")
print("Listo. Para generar, agrega LDRAW_LIBRARY_PATH=ldraw a tu archivo .env (ya viene así en .env.example).")
