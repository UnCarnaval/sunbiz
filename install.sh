#!/bin/bash
# Sunbiz Scraper — Instalación en Debian/Ubuntu
# Crea /opt/sunbiz, usuario sunbiz, servicio systemd y permisos adecuados.
# Uso:
#   wget https://raw.githubusercontent.com/UnCarnaval/sunbiz/main/install.sh
#   chmod +x install.sh
#   sudo ./install.sh

set -e

REPO_RAW="${REPO_RAW:-https://raw.githubusercontent.com/UnCarnaval/sunbiz/main}"
INSTALL_DIR="${INSTALL_DIR:-/opt/sunbiz}"
SERVICE_USER="${SERVICE_USER:-sunbiz}"
SERVICE_NAME="${SERVICE_NAME:-sunbiz}"

echo ""
echo "  Sunbiz Scraper — Instalador"
echo "  Repo: $REPO_RAW"
echo "  Destino: $INSTALL_DIR"
echo "  Usuario del servicio: $SERVICE_USER"
echo ""

# Solo root puede escribir en /opt y crear usuarios/servicios
if [ "$(id -u)" -ne 0 ]; then
    echo "Ejecuta con sudo: sudo ./install.sh"
    exit 1
fi

# Dependencias del sistema (antes de crear usuario)
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

# Usuario y grupo para ejecutar el servicio (sin login, sin home por defecto)
if ! getent group "$SERVICE_USER" >/dev/null 2>&1; then
    echo "==> Creando grupo $SERVICE_USER..."
    groupadd --system "$SERVICE_USER"
fi
if ! getent passwd "$SERVICE_USER" >/dev/null 2>&1; then
    echo "==> Creando usuario $SERVICE_USER..."
    useradd --system --gid "$SERVICE_USER" --no-create-home \
        --shell /usr/sbin/nologin --comment "Sunbiz Scraper" "$SERVICE_USER"
fi

mkdir -p "$INSTALL_DIR"
cd "$INSTALL_DIR"

# Descargar proyecto (main, bot Telegram, config de ejemplo, dependencias)
echo "==> Descargando proyecto..."
for f in main.py telegram_bot.py pyproject.toml config.ini.example; do
    curl -sSLo "$f" "$REPO_RAW/$f" || { echo "Error descargando $f"; exit 1; }
done
# config.ini solo si no existe (no sobrescribir configuración del usuario)
if [ ! -f "$INSTALL_DIR/config.ini" ]; then
    cp "$INSTALL_DIR/config.ini.example" "$INSTALL_DIR/config.ini"
    echo "==> Creado config.ini desde config.ini.example (edita token en [telegram])"
fi

# Venv + uv en el proyecto
echo "==> Configurando Python..."
python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q uv
.venv/bin/uv sync

# Navegador Camoufox
echo "==> Descargando navegador Camoufox..."
.venv/bin/uv run python -m camoufox fetch

# Wrapper para ejecutar fácil (CLI)
cat > "$INSTALL_DIR/run.sh" << 'RUN'
#!/bin/bash
cd "$(dirname "$0")"
exec .venv/bin/uv run main.py "$@"
RUN

# Wrapper para el bot de Telegram (instala python-telegram-bot vía pyproject.toml)
cat > "$INSTALL_DIR/run_bot.sh" << 'RUNBOT'
#!/bin/bash
cd "$(dirname "$0")"
exec .venv/bin/uv run telegram_bot.py "$@"
RUNBOT
chmod +x "$INSTALL_DIR/run_bot.sh"

# Permisos: dueño sunbiz, directorios 755, run.sh 755, ficheros de datos escribibles
echo "==> Ajustando permisos..."
chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"
chmod 755 "$INSTALL_DIR"
chmod 755 "$INSTALL_DIR/run.sh"
chmod 755 "$INSTALL_DIR/run_bot.sh"
chmod -R u+rX,g+rX,o+rX "$INSTALL_DIR"
chmod u+w "$INSTALL_DIR"
# .venv y binarios ejecutables
[ -d "$INSTALL_DIR/.venv" ] && chmod -R u+rwX "$INSTALL_DIR/.venv"

# Servicio systemd (oneshot: una ejecución; para uso interactivo ejecutar como sunbiz o con systemctl)
echo "==> Creando servicio systemd..."
cat > "/etc/systemd/system/${SERVICE_NAME}.service" << SVC
[Unit]
Description=Sunbiz Scraper
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/run.sh
StandardInput=null
# Permite que los ficheros generados (JSON, TXT) pertenezcan a sunbiz
UMask=0022

[Install]
WantedBy=multi-user.target
SVC

# Servicio systemd para el bot de Telegram (long-running)
echo "==> Creando servicio systemd para el bot de Telegram..."
cat > "/etc/systemd/system/${SERVICE_NAME}-bot.service" << SVCBOT
[Unit]
Description=Sunbiz Scraper — Bot de Telegram
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/run_bot.sh
Restart=on-failure
RestartSec=10
# Ficheros generados (JSON, TXT) en data_dir
UMask=0022

[Install]
WantedBy=multi-user.target
SVCBOT

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
# Bot no se habilita por defecto: hay que configurar config.ini (token) y luego enable/start

echo ""
echo "  Listo."
echo "  CLI:                  sudo -u $SERVICE_USER $INSTALL_DIR/run.sh"
echo "  Servicio CLI:         systemctl start $SERVICE_NAME"
echo ""
echo "  Bot Telegram:         sudo -u $SERVICE_USER $INSTALL_DIR/run_bot.sh"
echo "  Después de editar $INSTALL_DIR/config.ini (token en [telegram]):"
echo "                        sudo systemctl enable ${SERVICE_NAME}-bot"
echo "                        sudo systemctl start ${SERVICE_NAME}-bot"
echo "  Estado bot:           systemctl status ${SERVICE_NAME}-bot"
echo ""
