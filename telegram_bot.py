"""Bot de Telegram: recibe palabra clave y cantidad, devuelve TXT de direcciones Sunbiz."""

import asyncio
import configparser
from pathlib import Path

from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters

from main import fetch_sunbiz_data

CONFIG_PATH = Path(__file__).resolve().parent / "config.ini"

request_queue: asyncio.Queue[tuple[int, str, int]] = asyncio.Queue()
queue_lock = asyncio.Lock()
queue_size = 0


def load_config() -> configparser.ConfigParser:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"No existe {CONFIG_PATH}. Copia config.ini.example a config.ini y configura el token.")
    cfg = configparser.ConfigParser()
    cfg.read(CONFIG_PATH, encoding="utf-8")
    return cfg


def get_config() -> tuple[str, int, Path]:
    cfg = load_config()
    token = cfg.get("telegram", "token", fallback="").strip()
    if not token or token == "YOUR_BOT_TOKEN":
        raise ValueError("Configura token en config.ini [telegram]")
    max_addr = cfg.getint("telegram", "max_addresses", fallback=100)
    data_dir = Path(cfg.get("bot", "data_dir", fallback="data/bot"))
    data_dir = data_dir if data_dir.is_absolute() else Path(__file__).resolve().parent / data_dir
    return token, max_addr, data_dir


def run_fetch_sync(term: str, count: int, data_dir: Path, seen_path: Path, output_path: Path) -> Path | None:
    """Ejecuta fetch en hilo síncrono. Devuelve path del TXT generado o None si falla."""
    data_dir.mkdir(parents=True, exist_ok=True)
    try:
        results = fetch_sunbiz_data(
            search_term=term,
            max_results=count,
            output_path=str(output_path),
            seen_path=str(seen_path),
            headless=True,
        )
        if not results:
            return None
        term_clean = term.lower().replace(" ", "")
        txt_path = data_dir / f"{term_clean}{len(results)}.txt"
        return txt_path if txt_path.exists() else None
    except Exception:
        return None


async def queue_worker(app: Application, max_addresses: int, data_dir: Path) -> None:
    global queue_size
    bot = app.bot
    while True:
        try:
            chat_id, keyword, count = await request_queue.get()
            async with queue_lock:
                queue_size = max(0, queue_size - 1)
            count = min(count, max_addresses)
            await bot.send_message(
                chat_id=chat_id,
                text=f"Procesando: <b>{keyword}</b> — hasta {count} direcciones. Un momento…",
                parse_mode="HTML",
            )
            output_path = data_dir / "sunbiz_data.json"
            term_clean = keyword.lower().replace(" ", "")
            seen_path = data_dir / f"{term_clean}_seen.txt"
            loop = asyncio.get_event_loop()
            txt_path = await loop.run_in_executor(
                None,
                lambda: run_fetch_sync(keyword, count, data_dir, seen_path, output_path),
            )
            if txt_path is None or not txt_path.exists():
                await bot.send_message(
                    chat_id=chat_id,
                    text="No se encontraron direcciones nuevas o hubo un error. Prueba otra palabra o más adelante.",
                )
                continue
            with open(txt_path, "rb") as f:
                await bot.send_document(
                    chat_id=chat_id,
                    document=f,
                    filename=txt_path.name,
                    caption=f"Sunbiz — {keyword} ({txt_path.stat().st_size} bytes)",
                )
            txt_path.unlink(missing_ok=True)
        except asyncio.CancelledError:
            break
        except Exception as e:
            try:
                await bot.send_message(chat_id=chat_id, text=f"Error al procesar: {e!s}")
            except Exception:
                pass


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global queue_size
    if not update.message or not update.message.text:
        return
    text = update.message.text.strip()
    parts = text.split()
    if not parts:
        return
    keyword = parts[0]
    try:
        count = int(parts[1]) if len(parts) > 1 else 100
    except ValueError:
        await update.message.reply_text("Usa: palabra cantidad\nEjemplo: plumber 50")
        return
    max_addresses = context.bot_data.get("max_addresses", 100)
    count = min(max(1, count), max_addresses)
    await request_queue.put((update.effective_chat.id, keyword, count))
    async with queue_lock:
        queue_size += 1
    pos = queue_size
    await update.message.reply_text(
        f"En cola (posición {pos}). <b>{keyword}</b>, hasta <b>{count}</b> direcciones. "
        "Te enviaré el .txt cuando esté listo.",
        parse_mode="HTML",
    )


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Sunbiz Scraper — Envíame:\n\n"
        "<b>palabra cantidad</b>\n\n"
        "Ejemplo: <code>plumber 50</code>\n\n"
        "Te devolveré un .txt con direcciones (Principal Address). "
        "Hay un límite por petición y las peticiones se atienden en cola.",
        parse_mode="HTML",
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    max_addr = context.bot_data.get("max_addresses", 100)
    await update.message.reply_text(
        f"Envía un mensaje: <b>palabra cantidad</b>.\n"
        f"Límite por petición: <b>{max_addr}</b> direcciones.\n"
        "Las peticiones se procesan en cola, una a una.",
        parse_mode="HTML",
    )


def main() -> None:
    token, max_addresses, data_dir = get_config()
    data_dir.mkdir(parents=True, exist_ok=True)

    async def post_init(app: Application) -> None:
        app.bot_data["max_addresses"] = max_addresses
        app.bot_data["data_dir"] = data_dir
        asyncio.create_task(queue_worker(app, max_addresses, data_dir))

    app = (
        Application.builder()
        .token(token)
        .post_init(post_init)
        .build()
    )
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.Regex(r"^/start"), cmd_start))
    app.add_handler(MessageHandler(filters.Regex(r"^/help"), cmd_help))
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
