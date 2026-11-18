"""Demo local de Build What You Have. Solo escucha en esta laptop (127.0.0.1)."""
import base64, io, json, os, re, shutil, subprocess, sys, threading, time, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from PIL import Image, ImageOps
import cv2
import numpy as np

import bricks as B
import vision as V

DEMO = Path(__file__).resolve().parent
ROOT = DEMO.parent
DESIGNS = ROOT / "designs"
LIVE = DEMO / "records_live"
CACHE = DEMO / "cache"
INV_FILE = DEMO / "inventario.json"
EXE = shutil.which("brickwright", path=str(Path(sys.executable).parent)) or "brickwright"
CLAUDE = shutil.which("claude")
MODEL = os.environ.get("DEMO_MODEL", "haiku")
MAX_PARALLEL = 2
TIMEOUT = 600
GRACE = 20  # segundos que se espera al agente despues de finalizar el diseño
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


def child_env():
    """Entorno para los procesos hijos: usa la sesion de Claude Code, nunca una clave de API."""
    env = {k: v for k, v in os.environ.items() if not k.startswith(("CLAUDE", "ANTHROPIC"))}
    git_bash = os.environ.get("CLAUDE_CODE_GIT_BASH_PATH")
    if git_bash:
        env["CLAUDE_CODE_GIT_BASH_PATH"] = git_bash
    env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")
    env.update(LDRAW_LIBRARY_PATH=str(ROOT / read_env().get("LDRAW_LIBRARY_PATH", "ldraw")), PYTHONUTF8="1", PYTHONIOENCODING="utf8")
    return env


def friendly(text):
    """Convierte un error tecnico en un mensaje entendible."""
    low = " ".join(text.lower().split())
    if "hit your" in low or "usage limit" in low or "limit reached" in low:
        return "Se alcanzó el límite de uso de tu plan de Claude. Intenta cuando se renueve."
    if "not logged in" in low or "/login" in low or "authentication" in low:
        return "Claude Code no tiene la sesión iniciada en esta laptop."
    if "rate limit" in low or "overloaded" in low:
        return "El servicio está saturado. Intenta de nuevo en un momento."
    return None


TASK = """Create a LEGO build with BrickWright for one request. Work only on this file: {build}. Do not read or change any other project file.
build.py already contains a test named "inventory" that reports bricks over the limit and bricks still available: keep that test, do not weaken it, and repair the build when it fails.

Run these commands exactly as shown, one per Bash call, without cd or export:
- Read instructions once: brickwright external instructions
- Check: brickwright external validate {rid}
- Picture: brickwright external render {rid}   (then view {png})
- Finish: brickwright external finalize {rid}

Request and allowed bricks:
{prompt}

Follow the BrickWright instructions: edit build.py, validate, repair, render, finalize.
The build must be recognizable as the requested object, not just a stack of bricks: give it the object's real proportions (e.g. a table needs a flat wide top and legs, not a tall tower) and check the render for this before finalizing.
Use at most 8 validate calls. If the build is still not connected after 4 validate calls, simplify its SHAPE while keeping it recognizable (fewer bricks, but still proportioned like the object), not by stacking everything into one tall column. Always finish with finalize."""


def is_finalized(record):
    try:
        return json.loads((record / "meta.json").read_text(encoding="utf8")).get("finalized") is True
    except (OSError, ValueError):
        return False


def stop_tree(proc):
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
    else:
        proc.kill()


def run_agent(cmd, record, folder, env):
    """Corre al agente y lo detiene si, ya finalizado el diseño, el proceso no termina solo."""
    limit = time.time() + TIMEOUT
    done_at = None
    with open(folder / "run.log", "w", encoding="utf8") as log:
        proc = subprocess.Popen(cmd, cwd=str(folder), env=env, stdin=subprocess.DEVNULL, stdout=log,
                                stderr=subprocess.STDOUT, encoding="utf8", errors="replace")
        while proc.poll() is None:
            now = time.time()
            if now > limit:
                stop_tree(proc)
                raise subprocess.TimeoutExpired(cmd, TIMEOUT)
            if done_at is None and is_finalized(record):
                done_at = now
            if done_at is not None and now - done_at > GRACE:
                stop_tree(proc)
                proc.wait(timeout=20)
                break
            time.sleep(2)
    return proc


def run_job(jid, request, rows, min_bricks):
    job = jobs[jid]
    with slots:
        job.update(status="running", started=time.time())
        folder = LIVE / jid
        folder.mkdir(parents=True, exist_ok=True)
        prompt = f"{request}. " + B.inventory_prompt(rows, min_bricks)
        env = {**child_env(), "BRICKWRIGHT_RECORDS_DIR": str(folder)}
        try:
            subprocess.run([EXE, "external", "init", prompt], cwd=str(folder), env=env, capture_output=True, timeout=60, check=True)
            record = next(folder.glob("*/build.py")).parent
            rid = record.name
            build_py = record / "build.py"
            build_py.write_text(B.add_inventory_test(build_py.read_text(encoding="utf8"), rows, min_bricks), encoding="utf8")
            task = TASK.format(build=record / "build.py", rid=rid, png=record / "out" / "build.png", prompt=prompt)
            cmd = [CLAUDE, "-p", task, "--model", MODEL, "--no-session-persistence", "--strict-mcp-config",
                   "--allowedTools", "Read", "Edit", "Write", "Bash(brickwright external *)"]
            proc = run_agent(cmd, record, folder, env)
            if not (record / "out" / "build.ldr").exists() or not (record / "out" / "build.png").exists():
                text = (folder / "run.log").read_text(encoding="utf8", errors="replace")
                job.update(status="failed", error=friendly(text) or f"No se generó el diseño (código {proc.returncode}). Detalle en demo/records_live/{jid}/run.log")
                return
            data = json.loads((record / "meta.json").read_text(encoding="utf8"))
            data["demo_title"] = request
            (record / "meta.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf8")
            with lock:
                d = add_design(rid, record, request[:40], "En vivo")
            result = B.check(d["count"], inv_map(rows))
            job.update(status="done" if result["ok"] else "rejected", design=rid, check=result, valid=data.get("status") == "valid")
        except subprocess.TimeoutExpired:
            job.update(status="failed", error="Se agotó el tiempo de espera.")
        except Exception as exc:
            job.update(status="failed", error=f"Error inesperado: {type(exc).__name__}")
        finally:
            job["ended"] = time.time()


def read_photo(raw):
    """Devuelve la lista detectada y la foto con las piezas marcadas."""
    im = ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert("RGB")
    im.thumbnail((2000, 2000))
    rgb = np.array(im)
    pieces = V.detect(rgb)
    marked = rgb.copy()
    for p in pieces:
        cv2.polylines(marked, [np.array(p["box"], np.int32)], True, (255, 0, 200), 5)
    h, w = marked.shape[:2]
    small = Image.fromarray(cv2.resize(marked, (760, int(760 * h / w))))
    buf = io.BytesIO()
    small.save(buf, "JPEG", quality=82)
    return {"inventory": V.to_rows(pieces), "count": len(pieces),
            "image": "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()}


def suggest_ideas(rows):
    """Pide 3 ideas a Claude. El diseño lo hace despues el agente."""
    prompt = ("These are the LEGO bricks I own:\n" + B.inventory_prompt(rows) +
              "\nSuggest 3 simple, clearly recognizable objects that could be built well using only these bricks. "
              "Reply with only a JSON array of 3 short English noun phrases. Do not use any tools.")
    out = subprocess.run([CLAUDE, "-p", prompt, "--model", MODEL, "--no-session-persistence", "--strict-mcp-config"],
                         cwd=str(DEMO), env=child_env(), stdin=subprocess.DEVNULL, capture_output=True, timeout=120,
                         encoding="utf8", errors="replace")
    text = out.stdout or ""
    match = re.search(r"\[.*\]", text, re.S)
    if not match:
        raise RuntimeError(text + (out.stderr or ""))
    return [str(x)[:60] for x in json.loads(match[0])][:3]


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
            return self.send({"inventory": rows, "key": CLAUDE is not None, "parts": B.PART_NAMES,
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
        if self.path == "/api/photo":
            length = int(self.headers.get("Content-Length", 0))
            if not 0 < length <= 15_000_000:
                return self.send({"error": "La foto debe pesar menos de 15 MB."}, code=400)
            try:
                return self.send(read_photo(self.rfile.read(length)))
            except Exception:
                return self.send({"error": "No se pudo leer esa imagen."}, code=400)
        size = min(int(self.headers.get("Content-Length", 0)), 100_000)
        try:
            data = json.loads(self.rfile.read(size) or b"{}")
            if self.path == "/api/reset":
                INV_FILE.unlink(missing_ok=True)
                return self.send({"ok": True})
            if self.path == "/api/inventory":
                rows = validate_rows(data["inventory"])
                INV_FILE.write_text(json.dumps(rows, indent=1), encoding="utf8")
                return self.send({"ok": True})
            if self.path == "/api/ideas":
                if not CLAUDE:
                    return self.send({"error": "No encontré Claude Code en esta laptop."}, code=400)
                try:
                    return self.send({"ideas": suggest_ideas(load_inventory())})
                except Exception as exc:
                    return self.send({"error": friendly(str(exc)) or "No se pudieron obtener ideas."}, code=502)
            if self.path == "/api/generate":
                request = " ".join(str(data.get("request", "")).split())[:80]
                if not request:
                    return self.send({"error": "Escribe qué quieres construir."}, code=400)
                if not CLAUDE:
                    return self.send({"error": "No encontré Claude Code en esta laptop."}, code=400)
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
    port = int(os.environ.get("DEMO_PORT", "8765"))
    print(f"{len(designs)} diseños cargados. Abre http://127.0.0.1:{port}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
