"""Lee archivos LDraw (.ldr): cuenta piezas, compara con el inventario y separa por capas."""
from collections import Counter

# id LDraw -> (ancho, largo) en studs; el largo va sobre el eje X cuando no hay rotacion
PARTS = {"3005": (1, 1), "3004": (1, 2), "3010": (1, 4), "3009": (1, 6), "3003": (2, 2)}
PART_NAMES = {p: f"{w}×{l}" for p, (w, l) in PARTS.items()}

# codigo LDraw -> (nombre, color en pantalla, nombre en BrickLayer)
COLORS = {
    0: ("Negro", "#1B2A34", "BLACK"),
    15: ("Blanco", "#F2F2F2", "WHITE"),
    25: ("Naranja", "#FE8A18", "ORANGE"),
    10: ("Verde claro", "#4B9F4A", "BRIGHT_GREEN"),
    71: ("Gris", "#A0A5A9", "LIGHT_BLUISH_GRAY"),
    272: ("Azul oscuro", "#0A3463", "DARK_BLUE"),
    288: ("Verde oscuro", "#184632", "DARK_GREEN"),
    322: ("Celeste", "#36AEBF", "MEDIUM_AZURE"),
}

# Tus 36 piezas, contadas a mano desde la foto
DEFAULT_INVENTORY = [
    ("3005", 272, 9), ("3005", 322, 7), ("3005", 25, 8), ("3005", 10, 1),
    ("3004", 71, 1), ("3010", 0, 1),
    ("3009", 272, 1), ("3009", 15, 2), ("3009", 288, 1), ("3009", 25, 1),
    ("3003", 272, 1), ("3003", 288, 1), ("3003", 322, 1), ("3003", 0, 1),
]


def parse_ldr(text):
    """Devuelve las piezas del archivo sin ejecutar ningun codigo."""
    bricks = []
    for line in text.splitlines():
        t = line.split()
        if len(t) < 15 or t[0] != "1":
            continue
        part = t[14].lower().removesuffix(".dat")
        w, l = PARTS.get(part, (1, 1))
        if abs(float(t[5])) < 0.5:  # girada 90 grados
            w, l = l, w
        size_x, size_z = l, w
        x, y, z = float(t[2]), float(t[3]), float(t[4])
        bricks.append({
            "part": part,
            "color": int(t[1]),
            "level": round(-y / 24) - 1,
            "x": round((x - size_x * 10) / 20),
            "z": round((z - size_z * 10) / 20),
            "sx": size_x,
            "sz": size_z,
        })
    return bricks


def count(bricks):
    return Counter((b["part"], b["color"]) for b in bricks)


def check(used, inventory):
    """Compara lo usado con lo disponible. inventory: {(part, color): cantidad}."""
    missing = [
        {"part": p, "color": c, "need": n, "have": inventory.get((p, c), 0)}
        for (p, c), n in sorted(used.items())
        if n > inventory.get((p, c), 0)
    ]
    return {
        "ok": not missing,
        "used": sum(used.values()),
        "owned": sum(inventory.values()),
        "missing": missing,
    }


def inventory_prompt(rows, min_bricks=None):
    """Mismo formato de lista que se uso en las pruebas."""
    total = sum(r["qty"] for r in rows if r["qty"] > 0)
    lines = [
        f"You may use ONLY these {total} LEGO bricks. Each line is the maximum quantity "
        "of that exact part and color; you do not have to use them all."
    ]
    for r in rows:
        if r["qty"] > 0:
            part = r["part"]
            lines.append(f"{r['qty']} x brick {PART_NAMES[part]} (part {part}), Color.{COLORS[r['color']][2]}".replace("×", "x"))
    if min_bricks:
        lines.append(f"You must use at least {min_bricks} of these {total} bricks, while keeping the object recognizable.")
    return "\n".join(lines)
