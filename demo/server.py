"""Demo local de Build What You Have. Solo escucha en esta laptop (127.0.0.1)."""
import json, os, re, shutil, subprocess, sys, threading, time, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from PIL import Image
import numpy as np

import bricks as B

DEMO = Path(__file__).resolve().parent
ROOT = DEMO.parent
DESIGNS = ROOT / "designs"
LIVE = DEMO / "records_live"
CACHE = DEMO / "cache"
INV_FILE = DEMO / "inventario.json"
EXE = shutil.which("brickwright", path=str(Path(sys.executable).parent)) or "brickwright"
MODEL = os.environ.get("DEMO_MODEL", "anthropic/claude-haiku-5-5")
MAX_PARALLEL = 2
TIMEOUT = 600
ID_RE = re.compile(r"^[\w-]{5,120}$")

SETS = [("pedidos.tsv", "Solo la lista"), ("pedidos_b.tsv", "Usa muchas"),
        ("pedidos_c.tsv", "Al menos 30"), ("pedidos_d.tsv", "Al menos 30 + aviso")]
NAMES = {"a small robot": "Robot", "a bench": "Banco", "a dog": "Perro", "a house": "Casa", "a tree": "Árbol",
         "a bridge": "Puente", "a boat": "Barco", "a flower": "Flor", "a tower": "Torre", "a table": "Mesa"}

designs, records, jobs = {}, {}, {}
lock = threading.Lock()
slots = threading.Semaphore(MAX_PARALLEL)


def add_design(rid, path, title, group):
    ldr = path / "out" / "build.ldr"
    if not ldr.exists():
        return None
    pieces = B.parse_ldr(ldr.read_text(encoding="utf8"))
    designs[rid] = {"id": rid, "title": title, "group": group, "bricks": pieces, "count": B.count(pieces)}
    records[rid] = path
    return designs[rid]


def load_designs():
    for tsv, group in SETS:
        for line in (DESIGNS / tsv).read_text(encoding="utf8").splitlines():
            prompt, rid = line.split("\t")[:2]
            add_design(rid, DESIGNS / "records" / rid, NAMES.get(prompt, prompt), group)
    add_design("20261108-175051-a-small-robot-with-51e27d2c", DESIGNS / "records" / "20261108-175051-a-small-robot-with-51e27d2c",
               "Robot armado a mano", "Prueba inicial")
    for job in sorted(LIVE.glob("*")) if LIVE.exists() else []:
        for meta in job.glob("*/meta.json"):
            data = json.loads(meta.read_text(encoding="utf8"))
            title = data.get("demo_title") or data.get("prompt", "Pedido").split(". You may")[0]
            add_design(meta.parent.name, meta.parent, title[:40], "En vivo")


def load_inventory():
    if INV_FILE.exists():
        return json.loads(INV_FILE.read_text(encoding="utf8"))
    return [{"part": p, "color": c, "qty": q} for p, c, q in B.DEFAULT_INVENTORY]


def inv_map(rows):
    out = {}
    for r in rows:
        if r["qty"] > 0:
            out[(r["part"], r["color"])] = out.get((r["part"], r["color"]), 0) + r["qty"]
    return out


def validate_rows(rows):
    clean = []
    for r in rows:
        part, color, qty = str(r["part"]), int(r["color"]), int(r["qty"])
        if part not in B.PARTS or color not in B.COLORS or not 0 <= qty <= 500:
            raise ValueError("fila inválida")
        clean.append({"part": part, "color": color, "qty": qty})
    return clean


def read_env():
    """Lee ROOT/.env sin registrar sus valores."""
    values = {}
    path = ROOT / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                name, value = line.split("=", 1)
                values[name.strip()] = value.strip()
    return values


def read_key():
    return read_env().get("ANTHROPIC_API_KEY") or None


def run_job(jid, request, rows, min_bricks):
    job = jobs[jid]
    key = read_key()
    with slots:
        job.update(status="running", started=time.time())
        folder = LIVE / jid
        folder.mkdir(parents=True, exist_ok=True)
        prompt = f"{request}. " + B.inventory_prompt(rows, min_bricks)
        env = {**os.environ, "ANTHROPIC_API_KEY": key, "LDRAW_LIBRARY_PATH": str(ROOT / read_env().get("LDRAW_LIBRARY_PATH", "ldraw")), "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf8"}
        cmd = [str(EXE), "generate", prompt, "--records-dir", str(folder), "--model", MODEL,
               "--max-validations", "12", "--max-cost", "0.50"]
        try:
            with open(folder / "run.log", "w", encoding="utf8") as log:
                proc = subprocess.run(cmd, cwd=str(ROOT), env=env, stdout=log, stderr=subprocess.STDOUT, timeout=TIMEOUT)
            metas = list(folder.glob("*/meta.json"))
            if not metas or not (metas[0].parent / "out" / "build.ldr").exists():
                tail = (folder / "run.log").read_text(encoding="utf8", errors="replace")[-400:].replace(key, "***")
                job.update(status="failed", error=f"No se generó el diseño (código {proc.returncode}). {tail}")
                return
            meta = metas[0].parent
            data = json.loads((meta / "meta.json").read_text(encoding="utf8"))
            data["demo_title"] = request
            (meta / "meta.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf8")
            with lock:
                d = add_design(meta.name, meta, request[:40], "En vivo")
            result = B.check(d["count"], inv_map(rows))
            job.update(status="done" if result["ok"] else "rejected", design=meta.name, check=result,
                       valid=data.get("status") == "valid")
        except subprocess.TimeoutExpired:
            job.update(status="failed", error="Se agotó el tiempo de espera.")
        except Exception as exc:
            job.update(status="failed", error=str(exc).replace(key, "***"))
        finally:
            job["ended"] = time.time()


def thumb(rid):
    target = CACHE / f"{rid}.png"
    if not target.exists():
        CACHE.mkdir(exist_ok=True)
        im = Image.open(records[rid] / "out" / "build.png").convert("RGB")
        w, h = im.size
        arr = np.asarray(im.crop((w // 2, h // 2, w, h)).resize((480, 480)), dtype=np.float32)
        a = np.clip((arr.max(axis=2) - 4) / 16, 0, 1)[..., None]
        out = arr * a + np.array([0xEE, 0xE9, 0xF7], dtype=np.float32) * (1 - a)
        Image.fromarray(out.astype(np.uint8)).save(target)
    return target.read_bytes()


def summary(d, inv):
    return {"id": d["id"], "title": d["title"], "group": d["group"], **B.check(d["count"], inv)}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, body, ctype="application/json", code=200):
        if not isinstance(body, bytes):
            body = json.dumps(body, ensure_ascii=False).encode("utf8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/":
            return self.send((DEMO / "index.html").read_bytes(), "text/html; charset=utf-8")
        if path == "/api/state":
            rows = load_inventory()
            return self.send({"inventory": rows, "key": read_key() is not None, "parts": B.PART_NAMES,
                              "colors": {c: {"name": v[0], "hex": v[1]} for c, v in B.COLORS.items()}})
        if path == "/api/designs":
            inv = inv_map(load_inventory())
            with lock:
                return self.send([summary(d, inv) for d in designs.values()])
        if path == "/api/jobs":
            return self.send(sorted(jobs.values(), key=lambda j: j["created"], reverse=True))
        m = re.match(r"^/api/design/([\w-]+)$", path)
        if m and m[1] in designs:
            d = designs[m[1]]
            return self.send({**summary(d, inv_map(load_inventory())), "bricks": d["bricks"]})
        m = re.match(r"^/img/([\w-]+)\.png$", path)
        if m and m[1] in records and ID_RE.match(m[1]):
            return self.send(thumb(m[1]), "image/png")
        self.send({"error": "no encontrado"}, code=404)

    def do_POST(self):
        size = min(int(self.headers.get("Content-Length", 0)), 100_000)
        try:
            data = json.loads(self.rfile.read(size) or b"{}")
            if self.path == "/api/inventory":
                rows = validate_rows(data["inventory"])
                INV_FILE.write_text(json.dumps(rows, indent=1), encoding="utf8")
                return self.send({"ok": True})
            if self.path == "/api/generate":
                request = " ".join(str(data.get("request", "")).split())[:80]
                if not request:
                    return self.send({"error": "Escribe qué quieres construir."}, code=400)
                if read_key() is None:
                    return self.send({"error": "Falta la clave de API en .env."}, code=400)
                rows = load_inventory()
                total = sum(r["qty"] for r in rows)
                min_bricks = int(total * .8) if data.get("use_most") else None
                jid = time.strftime("%H%M%S-") + uuid.uuid4().hex[:6]
                jobs[jid] = {"id": jid, "request": request, "status": "queued", "created": time.time()}
                threading.Thread(target=run_job, args=(jid, request, rows, min_bricks), daemon=True).start()
                return self.send(jobs[jid])
        except (ValueError, KeyError, TypeError) as exc:
            return self.send({"error": f"Datos inválidos: {exc}"}, code=400)
        self.send({"error": "no encontrado"}, code=404)


if __name__ == "__main__":
    load_designs()
    print(f"{len(designs)} diseños cargados. Abre http://127.0.0.1:8765", flush=True)
    ThreadingHTTPServer(("127.0.0.1", 8765), Handler).serve_forever()
