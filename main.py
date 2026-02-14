"""Scraper de búsqueda de corporaciones Sunbiz usando Camoufox."""

import json
import re
from pathlib import Path
from typing import Callable
from urllib.parse import quote

from camoufox.sync_api import Camoufox  # type: ignore[import-untyped]

BASE_URL = "https://search.sunbiz.org"
SEARCH_TERM = "PLUMBER"  # Intercambiable: "WATER", "PLUMBER", etc.
OUTPUT_JSON = "sunbiz_data.json"

# Patrón para detectar PO Box en todas sus presentaciones
PO_BOX_PATTERN = re.compile(
    r"\b(?:p\.?\s*o\.?\s*box|post\s*office\s*box|p\.?o\.?\.?box)\b",
    re.IGNORECASE,
)


def build_search_url(term: str = SEARCH_TERM) -> str:
    """Construye la URL de búsqueda Sunbiz con el término indicado."""
    encoded = quote(term, safe="")
    return (
        f"{BASE_URL}/Inquiry/CorporationSearch/SearchResults"
        f"?InquiryType=EntityName&inquiryDirectionType=ForwardList"
        f"&searchNameOrder={encoded}911%20P010000464770&SearchTerm={encoded}"
        f"&entityId=P01000046477&listNameOrder={encoded}2WINEPAINTINGRENOVATION%20L250000424390"
    )


DEFAULT_SEARCH_URL = build_search_url()


def _is_po_box_or_empty(text: str) -> bool:
    """True si el texto está vacío o es una dirección tipo PO Box."""
    if not text or not text.strip():
        return True
    return bool(PO_BOX_PATTERN.search(text))


def _normalize_address(addr: str) -> str:
    """Una sola línea, espacios normalizados, para comparar o guardar en seen."""
    return " ".join(addr.replace("\n", " ").split()).strip()


def _has_valid_address(details: dict[str, str]) -> bool:
    """True si hay al menos un valor que parezca dirección física (no vacía, no PO Box)."""
    for key, value in details.items():
        if "address" in key.lower() and value:
            if not _is_po_box_or_empty(value):
                return True
    return False


def _get_next_list_url(page) -> str | None:
    """Devuelve la URL del enlace 'Next List' o None si no existe."""
    link = page.locator('a[title="Next List"]').first
    if link.count() == 0:
        return None
    href = link.get_attribute("href")
    if not href:
        return None
    return BASE_URL + href if href.startswith("/") else href


def _extract_detail_sections(page) -> dict[str, str]:
    """Extrae todas las secciones .detailSection de la página de detalle."""
    sections = {}
    for section in page.locator("div.detailSection").all():
        spans = section.locator("span").all()
        if len(spans) < 2:
            continue
        label = spans[0].inner_text().strip()
        value = spans[1].inner_text().strip()
        if label:
            sections[label] = value
    return sections


def _extract_search_results(page) -> list[dict]:
    """Extrae filas de la tabla de resultados (nombre, documento, estado, href)."""
    rows = []
    for tr in page.locator("#search-results table tbody tr").all():
        cells = tr.locator("td").all()
        if len(cells) < 3:
            continue
        link = cells[0].locator("a").first
        if not link.count():
            continue
        corporate_name = link.inner_text().strip()
        href = link.get_attribute("href") or ""
        document_number = cells[1].inner_text().strip()
        status = cells[2].inner_text().strip()
        rows.append({
            "corporate_name": corporate_name,
            "document_number": document_number,
            "status": status,
            "detail_path": href,
        })
    return rows


def fetch_sunbiz_data(
    search_url: str | None = None,
    search_term: str | None = None,
    max_results: int | None = None,
    output_path: str | Path = OUTPUT_JSON,
    headless: bool = True,
    on_progress: Callable[[int], None] | None = None,
    seen_path: Path | str | None = None,
) -> list[dict]:
    """
    Obtiene datos de Sunbiz: resultados de búsqueda y detalle de cada entidad.

    - search_term: palabra a buscar (ej. "PLUMBER", "WATER"); usa SEARCH_TERM si no se pasa.
    - max_results: número máximo de entidades a extraer (solo con dirección válida); None = todas.
    - on_progress: callback opcional llamado con la cantidad actual de resultados extraídos.
    - seen_path: archivo con direcciones ya guardadas (una por línea); evita repetir en futuras búsquedas del mismo término.
    """
    if search_url is None:
        search_url = build_search_url(search_term or SEARCH_TERM)
    results: list[dict] = []

    seen: set[str] = set()
    if seen_path:
        p = Path(seen_path)
        if p.exists():
            seen = {line.strip() for line in p.read_text(encoding="utf-8").splitlines() if line.strip()}

    with Camoufox(headless=headless) as browser:
        page = browser.new_page()
        current_url: str | None = search_url

        while current_url:
            page.goto(current_url, wait_until="domcontentloaded")
            page.wait_for_load_state("networkidle", timeout=15000)

            rows = _extract_search_results(page)
            for row in rows:
                if max_results is not None and len(results) >= max_results:
                    break
                detail_path = row.pop("detail_path")
                detail_url = BASE_URL + detail_path if detail_path.startswith("/") else detail_path

                page.goto(detail_url, wait_until="domcontentloaded")
                page.wait_for_load_state("networkidle", timeout=15000)

                details = _extract_detail_sections(page)
                if not _has_valid_address(details):
                    continue
                addr = details.get("Principal Address", "").strip()
                if not addr:
                    continue
                normalized = _normalize_address(addr)
                if normalized in seen:
                    continue
                seen.add(normalized)
                results.append({
                    "corporate_name": row["corporate_name"],
                    "document_number": row["document_number"],
                    "status": row["status"],
                    "detail_url": detail_url,
                    "details": details,
                })
                if on_progress:
                    on_progress(len(results))

            if max_results is not None and len(results) >= max_results:
                break
            page.goto(current_url, wait_until="domcontentloaded")
            page.wait_for_load_state("networkidle", timeout=15000)
            current_url = _get_next_list_url(page)

    path = Path(output_path)
    path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")

    term_used = (search_term or SEARCH_TERM).lower().replace(" ", "")
    txt_name = f"{term_used}{len(results)}.txt"
    txt_path = path.parent / txt_name
    with txt_path.open("w", encoding="utf-8") as f:
        for item in results:
            addr = item.get("details", {}).get("Principal Address", "").strip()
            if addr:
                f.write(addr.replace("\n", " ") + "\n")

    if seen_path and seen:
        Path(seen_path).write_text("\n".join(sorted(seen)), encoding="utf-8")

    return results


if __name__ == "__main__":
    from rich.console import Console
    from rich.panel import Panel
    from rich.prompt import Prompt
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich.table import Table

    console = Console()

    console.print()
    console.print(
        Panel(
            "[bold cyan]Sunbiz[/] [white]Scraper[/] — Búsqueda de corporaciones Florida",
            border_style="cyan",
            padding=(0, 2),
            title="[bold white]🔍[/]",
            subtitle="[dim]search.sunbiz.org[/]",
        )
    )
    console.print()

    while True:
        palabra = Prompt.ask(
            "[bold cyan]Palabra a buscar[/]",
            default=SEARCH_TERM,
            show_default=True,
        ).strip() or SEARCH_TERM

        limite = Prompt.ask(
            "[bold cyan]¿Cuántas direcciones extraer?[/] [dim](Enter = todas)[/]",
            default="",
        ).strip()
        max_results = int(limite) if limite.isdecimal() else None

        if max_results is not None:
            console.print(f"  [dim]Límite: [cyan]{max_results}[/] direcciones válidas (sin repetir ya guardadas)[/]")
        else:
            console.print("  [dim]Sin límite — se extraerán todas las listas (omitiendo ya guardadas)[/]")
        console.print()

        path = Path(OUTPUT_JSON)
        term_used = palabra.lower().replace(" ", "")
        seen_path = path.parent / f"{term_used}_seen.txt"

        with Progress(
            SpinnerColumn(style="cyan"),
            TextColumn("[bold cyan]{task.description}[/]"),
            console=console,
        ) as progress:
            task = progress.add_task("Extrayendo datos...", total=None)

            def on_progress(n: int) -> None:
                progress.update(task, description=f"Extrayendo datos... [green]{n}[/] obtenidas")

            results = fetch_sunbiz_data(
                search_term=palabra,
                max_results=max_results,
                on_progress=on_progress,
                seen_path=seen_path,
            )

        txt_name = f"{term_used}{len(results)}.txt"
        txt_path = path.parent / txt_name

        console.print()
        console.print(
            Panel(
                f"[green]{len(results)}[/] direcciones guardadas (nuevas, sin duplicados)",
                border_style="green",
                title="[bold green]✓ Listo[/]",
                padding=(0, 2),
            )
        )

        table = Table(show_header=True, header_style="bold cyan", border_style="dim")
        table.add_column("Archivo", style="white")
        table.add_column("Ruta", style="dim")
        table.add_row("JSON", str(path.resolve()))
        table.add_row("TXT (direcciones)", str(txt_path.resolve()))
        table.add_row("Seen (historial)", str(seen_path.resolve()))
        console.print(table)
        console.print()

        otra = Prompt.ask(
            "[bold cyan]¿Otra búsqueda?[/] [dim](s/n)[/]",
            default="s",
        ).strip().lower()
        if otra.startswith("n"):
            console.print("[dim]Cerrando...[/]")
            break
        console.print()
