# Build What You Have

Pide algo y un agente de IA lo diseña usando solo las piezas de LEGO que tienes.
Demo local para el póster GEN-02 de WAIMLAp 2026. Usa [BrickWright](https://github.com/AvaLovelace1/brickwright) sin modificarlo.

## Qué hay

| Carpeta | Contenido |
|---|---|
| `demo/server.py` | Servidor local, solo accesible desde esta computadora |
| `demo/bricks.py` | Conteo de piezas e instrucciones por capas, leyendo archivos LDraw |
| `demo/index.html` | Interfaz |
| `designs/` | Los 40 diseños del piloto y el robot armado a mano |

## Estado

| Función | Estado |
|---|---|
| Lista editable de piezas | Funciona |
| Conteo: usadas ≤ disponibles | Funciona |
| Galería e instrucciones por capas | Funciona, sin internet |
| Generar un diseño nuevo | Conectado, sin probar todavía |
| "Surprise me" | Pendiente |
| Leer las piezas desde una foto | Pendiente |

## Cómo correrlo (Windows)

```bash
uv venv .venv --python 3.12
uv pip install --python .venv/Scripts/python.exe -r requirements.txt
.venv/Scripts/python.exe demo/server.py
```

Abre <http://127.0.0.1:8765>.

Para generar diseños nuevos, copia `.env.example` como `.env`, agrega tu clave de API e indica la carpeta de la [biblioteca LDraw](https://library.ldraw.org/). Sin eso, la galería y el conteo funcionan igual.

## Seguridad

El agente escribe y ejecuta código en tu computadora. El servidor escucha solo en `127.0.0.1`: no lo expongas a internet sin aislar cada ejecución en un contenedor.
