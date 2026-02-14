#!/bin/bash
# Sunbiz Scraper — Instalación en Debian/Ubuntu
# Uso:
#   wget https://raw.githubusercontent.com/TU_USUARIO/TU_REPO/main/install.sh
#   chmod +x install.sh
#   sudo ./install.sh

set -e

# Cambiar por tu usuario y repo de GitHub
REPO_RAW="${REPO_RAW:-https://raw.githubusercontent.com/TU_USUARIO/sunbiz/main}"
INSTALL_DIR="${INSTALL_DIR:-/opt/sunbiz}"

echo ""
echo "  Sunbiz Scraper — Instalador"
echo "  Repo: $REPO_RAW"
echo "  Destino: $INSTALL_DIR"
echo ""

# Solo root puede escribir en /opt
if [ "$(id -u)" -ne 0 ]; then
    echo "Ejecuta con sudo: sudo ./install.sh"
    exit 1
fi

mkdir -p "$INSTALL_DIR"
cd "$INSTALL_DIR"

# Descargar proyecto
echo "==> Descargando proyecto..."
for f in main.py pyproject.toml; do
    curl -sSLo "$f" "$REPO_RAW/$f" || { echo "Error descargando $f"; exit 1; }
done

# Dependencias del sistema
echo "==> Instalando dependencias del sistema..."
apt-get update -qq
apt-get install -y \
    python3 \
    python3-venv \
    python3-pip \
    curl \
    libgtk-3-0 \
    libx11-xcb1 \
    libasound2 \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libdbus-1-3 \
    libxshmfence1 \
    fonts-liberation

# Venv + uv en el proyecto
echo "==> Configurando Python..."
python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q uv
.venv/bin/uv sync

# Navegador Camoufox
echo "==> Descargando navegador Camoufox..."
.venv/bin/uv run python -m camoufox fetch

# Dejar que el usuario que invocó sudo sea dueño (para ejecutar sin root después)
if [ -n "$SUDO_USER" ]; then
    chown -R "$SUDO_USER" "$INSTALL_DIR"
fi

# Wrapper para ejecutar fácil
cat > "$INSTALL_DIR/run.sh" << 'RUN'
#!/bin/bash
cd "$(dirname "$0")"
exec .venv/bin/uv run main.py "$@"
RUN
chmod +x "$INSTALL_DIR/run.sh"
[ -n "$SUDO_USER" ] && chown "$SUDO_USER" "$INSTALL_DIR/run.sh"

echo ""
echo "  Listo."
echo "  Ejecutar:  $INSTALL_DIR/run.sh"
echo "  O:         cd $INSTALL_DIR && ./run.sh"
echo ""
