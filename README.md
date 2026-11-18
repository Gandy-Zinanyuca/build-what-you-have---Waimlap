# Build What You Have

**ES:** pide un objeto y un agente de IA lo diseña con LEGO usando **solo las piezas que tienes**.
**EN:** ask for an object and an LLM agent designs it with LEGO using **only the bricks you own**.

Demo del póster GEN-02 de WAIMLAp 2026, *Build What You Have: Applying an LLM Agent to Design with the Bricks You Own*.
Usa [BrickWright](https://github.com/AvaLovelace1/brickwright) sin modificarlo. Corre en tu computadora; nada se envía a un servidor propio.

> **Video de la demo:** _(se agrega aquí)_

## Pruébalo en 3 minutos (sin cuenta ni claves)

Necesitas [Python 3.12](https://www.python.org/downloads/) y [uv](https://docs.astral.sh/uv/getting-started/installation/).

```bash
git clone https://github.com/Gandy-Zinanyuca/build-what-you-have---Waimlap.git
cd build-what-you-have---Waimlap
uv venv .venv --python 3.12
uv pip install --python .venv/Scripts/python.exe -r requirements.txt   # Windows
uv pip install --python .venv/bin/python -r requirements.txt           # macOS / Linux
python demo/server.py        # o: .venv/Scripts/python.exe demo/server.py
```

Abre <http://127.0.0.1:8765> y prueba:

1. **Foto → lista de piezas.** En "Leer desde una foto" sube `samples/fotos_piezas.jpg` (o tu propia foto de piezas separadas, vistas desde arriba, sobre un fondo liso). Marca las piezas que detecta; en la foto de muestra encuentra las 36 y 1 falso positivo (un pliegue de la tela), que corriges con − .
2. **Lista editable.** Cambia las cantidades con + y −. La galería se actualiza sola.
3. **Galería de 41 diseños** (los 40 del piloto y un robot armado a mano), filtrada por los que puedes armar con tus piezas. Ábrelos para ver el conteo y las **instrucciones capa por capa**.

## Generar diseños nuevos (opcional)

Necesita [Claude Code](https://claude.com/claude-code) con tu sesión iniciada (usa tu plan; no pide clave de API) y la biblioteca de piezas:

```bash
python tools/get_ldraw.py          # descarga ~147 MB en ./ldraw
cp .env.example .env               # ya apunta a ./ldraw
```

Reinicia el servidor, escribe un pedido ("un perro") o pulsa **Sorpréndeme** para recibir 3 ideas.

Antes de probarlo, ten esto en cuenta:

- **Tarda de 4 a 10 minutos** por diseño, y **a veces falla**: en nuestras pruebas en vivo un diseño se pasó de las piezas y otro no terminó. Cuando se pasa, el conteo independiente lo rechaza.
- Gasta parte de tu cuota de Claude.
- Solo se ejecutan dos pedidos a la vez.

## Estado

| Función | Estado |
|---|---|
| Lista editable y conteo independiente (usadas ≤ disponibles) | Funciona |
| Galería e instrucciones por capas | Funciona, sin internet |
| Leer piezas desde una foto | Funciona con foto controlada; calibrado con una sola foto, sin validar con otras |
| Botón "Tomar foto" con la cámara de la laptop | Sin probar con una cámara real |
| Generar un diseño nuevo | Funciona a veces; lento y no siempre termina |
| Sorpréndeme | Funciona |

## Qué hay en el repositorio

| Ruta | Contenido |
|---|---|
| `demo/server.py` | Servidor local, solo accesible desde tu computadora |
| `demo/vision.py` | Lectura de piezas desde una foto (OpenCV, sin entrenamiento) |
| `demo/bricks.py` | Conteo e instrucciones por capas a partir de archivos LDraw |
| `demo/index.html` | Interfaz |
| `designs/` | Los 40 diseños del piloto y el robot armado a mano |
| `samples/` | Foto de ejemplo con 36 piezas |
| `tools/` | Descarga de LDraw y grabación de la demo |

## Seguridad

El agente escribe y ejecuta código en tu computadora. El servidor escucha solo en `127.0.0.1`: no lo expongas a una red sin aislar cada ejecución en un contenedor.

## Limitaciones del estudio

Una colección de 36 piezas, un modelo (Claude Haiku 5.5), 10 pedidos en inglés por condición; el reconocimiento lo juzgó un modelo, no personas, y la estabilidad física no se midió.

## Licencias

El código de este repositorio no incluye todavía una licencia; BrickWright es MIT y la biblioteca LDraw tiene su propia licencia.
