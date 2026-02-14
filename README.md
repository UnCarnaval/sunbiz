# Sunbiz Scraper

CLI para extraer datos de corporaciones desde [search.sunbiz.org](https://search.sunbiz.org) (Florida). Obtiene resultados por palabra clave, recorre las listas paginadas y guarda direcciones principales en JSON y TXT, omitiendo PO Box y duplicados.

## Requisitos

- Python 3.12+
- [uv](https://github.com/astral-sh/uv) (recomendado) o pip

## Instalación

### En tu máquina (con uv)

```bash
git clone https://github.com/TU_USUARIO/sunbiz.git
cd sunbiz
uv sync
uv run python -m camoufox fetch
```

### En servidor Debian/Ubuntu (instalador en 3 pasos)

Sustituye `TU_USUARIO` y `sunbiz` por tu usuario y repo en GitHub:

```bash
wget https://raw.githubusercontent.com/TU_USUARIO/sunbiz/main/install.sh
chmod +x install.sh
sudo ./install.sh
```

Instala en `/opt/sunbiz` y deja listo un ejecutable: `/opt/sunbiz/run.sh`.

## Uso

```bash
uv run main.py
# o, si usaste install.sh:
/opt/sunbiz/run.sh
```

El programa pide:

1. **Palabra a buscar** — Ej.: `plumber`, `water`. Por defecto: `PLUMBER`.
2. **¿Cuántas direcciones extraer?** — Número (ej. `300`) o Enter para todas.
3. Al terminar: **¿Otra búsqueda? (s/n)** — Repetir con otra palabra o salir.

Recorre automáticamente todas las páginas de resultados (“Next List”) hasta alcanzar el límite o el final. Descarta direcciones vacías y PO Box (cualquier variante: P.O. Box, PO Box, etc.).

## Salidas

| Archivo | Contenido |
|--------|-----------|
| `sunbiz_data.json` | Todas las entidades: nombre, documento, estado, URL y detalles (Filing, Principal Address, Mailing, etc.). |
| `{palabra}{n}.txt` | Solo **Principal Address**, una por línea, en una sola línea (ej. `plumber300.txt` si pediste 300 y la palabra fue `plumber`). |
| `{palabra}_seen.txt` | Historial de direcciones ya guardadas para esa palabra; evita repetir en futuras búsquedas. |

## Sin duplicados

Para cada palabra de búsqueda se mantiene un archivo `{palabra}_seen.txt`. Si más adelante vuelves a buscar la misma palabra, no se añaden de nuevo las direcciones que ya estaban guardadas; solo se agregan las nuevas.

## Uso programático

```python
from main import fetch_sunbiz_data

# Búsqueda con límite y archivo de historial
results = fetch_sunbiz_data(
    search_term="plumber",
    max_results=100,
    output_path="salida.json",
    seen_path="plumber_seen.txt",
)
```

## Licencia

Uso bajo tu responsabilidad; respeta los términos de uso del sitio y el tráfico que generes.
