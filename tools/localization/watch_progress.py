#!/usr/bin/env python3

import argparse
import json
import sys
import time
from collections import deque
from datetime import datetime
from pathlib import Path

from agent_batch import (
    SYSTEM_ID_PREFIXES,
    catalog_lock,
    effective_entry_list,
    eligible_entries,
    lease_expiration_text,
    lease_registry_path,
    load_lease_registry,
    needs_translation,
    prune_leases,
)
from project import load_project, resolve_project_path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INTERVAL = 10.0
DEFAULT_RATE_WINDOW_MINUTES = 5.0
COMPLETED_STATUSES = {"translated", "reviewed"}


def completed_entry_ids(data, mode):
    completed = set()
    for entry in effective_entry_list(data):
        entry_id = entry.get("id")
        source = entry.get("source")
        translation = entry.get("translation")
        if (
            not isinstance(entry_id, str)
            or not entry_id.strip()
            or entry_id.startswith(SYSTEM_ID_PREFIXES)
            or not isinstance(source, str)
            or not source
            or entry.get("status") not in COMPLETED_STATUSES
            or not isinstance(translation, str)
            or not translation
            or needs_translation(entry, mode)
        ):
            continue
        completed.add(entry_id)
    return completed


def progress_snapshot(project_path, mode):
    project = load_project(project_path)
    catalog_path = resolve_project_path(project, "catalog").resolve(strict=True)
    registry_path = lease_registry_path(catalog_path)

    with catalog_lock(catalog_path):
        data = json.loads(catalog_path.read_text(encoding="utf-8"))
        registry = load_lease_registry(registry_path, catalog_path)
        prune_leases(registry)

    eligible = eligible_entries(data, len(data.get("entries", [])), mode)
    eligible_ids = {entry["id"] for entry in eligible}
    completed_ids = completed_entry_ids(data, mode)
    reserved_ids = {
        entry_id
        for lease in registry["leases"]
        for entry_id in lease.get("entry_ids", [])
        if entry_id in eligible_ids
    }
    total = len(completed_ids) + len(eligible_ids)
    completed = len(completed_ids)

    return {
        "project": project["name"],
        "language": project["language"],
        "completed": completed,
        "total": total,
        "progress_percent": 100.0 if total == 0 else completed * 100.0 / total,
        "eligible": len(eligible_ids),
        "reserved": len(reserved_ids),
        "available": len(eligible_ids - reserved_ids),
        "active_batches": [
            {
                "worker": lease["worker"],
                "entries": len(lease.get("entry_ids", [])),
                "expires_at": lease_expiration_text(lease["expires_at"]),
            }
            for lease in registry["leases"]
        ],
    }


def format_integer(value):
    return f"{value:,}".replace(",", ".")


def format_decimal(value, digits=2):
    return f"{value:.{digits}f}".replace(".", ",")


def format_signed(value):
    sign = "+" if value >= 0 else "-"
    return f"{sign}{format_integer(abs(value))}"


def format_duration(seconds):
    total_minutes = max(0, int(seconds // 60))
    days, remaining_minutes = divmod(total_minutes, 24 * 60)
    hours, minutes = divmod(remaining_minutes, 60)
    if days:
        return f"{days}d {hours}h {minutes}m"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def format_elapsed(seconds):
    total_seconds = max(0, int(seconds))
    if total_seconds < 60:
        return f"{total_seconds}s"
    minutes, remaining_seconds = divmod(total_seconds, 60)
    if minutes < 60:
        return f"{minutes}m {remaining_seconds}s"
    hours, remaining_minutes = divmod(minutes, 60)
    return f"{hours}h {remaining_minutes}m"


def progress_bar(percent, width=32):
    bounded = max(0.0, min(100.0, percent))
    filled = round(width * bounded / 100.0)
    return f"[{'#' * filled}{'-' * (width - filled)}]"


def prune_rate_samples(samples, now, window_seconds):
    cutoff = now - window_seconds
    while len(samples) > 1 and samples[1][0] < cutoff:
        samples.popleft()


def calculate_recent_rate(samples):
    if len(samples) < 2:
        return 0.0
    first_time, first_completed = samples[0]
    last_time, last_completed = samples[-1]
    elapsed = last_time - first_time
    completed = max(0, last_completed - first_completed)
    return 0.0 if elapsed <= 0 else completed * 60.0 / elapsed


def activity_state(snapshot, recent_rate, elapsed, window_seconds):
    if snapshot["eligible"] == 0:
        return "COMPLETADO"
    if not snapshot["active_batches"]:
        return "DETENIDO (sin lotes activos)"
    if recent_rate > 0:
        return "AVANZANDO"
    if elapsed < window_seconds:
        return "ESPERANDO APLICACIÓN"
    return "SIN AVANCE RECIENTE"


def render_snapshot(
    snapshot,
    baseline,
    previous,
    elapsed,
    interval,
    recent_rate,
    rate_window_minutes,
    last_progress_elapsed,
):
    completed = snapshot["completed"]
    window_seconds = rate_window_minutes * 60.0
    state = activity_state(snapshot, recent_rate, elapsed, window_seconds)
    displayed_rate = recent_rate if snapshot["active_batches"] else 0.0
    window_label = format_decimal(rate_window_minutes, 0)
    lines = [
        f"Proyecto: {snapshot['project']} ({snapshot['language']})",
        (
            f"Actualizado: {datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')}"
            f" | cada {format_decimal(interval, 1)}s"
        ),
        "",
        (
            f"Progreso: {progress_bar(snapshot['progress_percent'])} "
            f"{format_decimal(snapshot['progress_percent'])}%"
        ),
        (
            f"Traducciones completadas: {format_integer(completed)} / "
            f"{format_integer(snapshot['total'])}"
        ),
        f"Entradas incompletas: {format_integer(snapshot['eligible'])}",
        f"Agregadas desde el inicio: {format_signed(completed - baseline)}",
        f"Agregadas en el último intervalo: {format_signed(completed - previous)}",
        f"Estado: {state}",
        (
            f"Ritmo reciente (últimos {window_label} min): "
            f"{format_decimal(displayed_rate)} entradas/min"
        ),
    ]
    if last_progress_elapsed is None:
        lines.append(
            "Último avance: sin avances desde que inició el monitor "
            f"({format_elapsed(elapsed)})"
        )
    else:
        lines.append(f"Último avance: hace {format_elapsed(last_progress_elapsed)}")
    if displayed_rate > 0 and snapshot["eligible"]:
        eta_seconds = snapshot["eligible"] * 60.0 / displayed_rate
        lines.append(f"Tiempo restante estimado: {format_duration(eta_seconds)}")

    lines.extend([
        "",
        f"Entradas reservadas: {format_integer(snapshot['reserved'])}",
        f"Entradas disponibles: {format_integer(snapshot['available'])}",
        f"Lotes activos: {len(snapshot['active_batches'])}",
    ])
    for lease in snapshot["active_batches"]:
        lines.append(
            f"  {lease['worker']}: {lease['entries']} entradas, vence {lease['expires_at']}"
        )
    lines.extend(["", "Ctrl+C para detener el monitor."])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Monitoriza el progreso de una cola de traducción en tiempo real."
    )
    parser.add_argument(
        "--project",
        type=Path,
        default=ROOT / "config" / "project.json",
        help="Configuración del proyecto (predeterminado: config/project.json)",
    )
    parser.add_argument(
        "--mode",
        choices=("pending", "incomplete"),
        default="incomplete",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=DEFAULT_INTERVAL,
        help="Segundos entre actualizaciones (predeterminado: 10)",
    )
    parser.add_argument(
        "--rate-window",
        type=float,
        default=DEFAULT_RATE_WINDOW_MINUTES,
        help="Minutos usados para el ritmo reciente (predeterminado: 5)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Muestra una sola actualización y termina",
    )
    parser.add_argument(
        "--no-clear",
        action="store_true",
        help="No limpia la terminal entre actualizaciones",
    )
    args = parser.parse_args()
    if args.interval < 1:
        parser.error("--interval debe ser de al menos 1 segundo")
    if args.rate_window < 1:
        parser.error("--rate-window debe ser de al menos 1 minuto")

    baseline = None
    previous = None
    last_progress_at = None
    samples = deque()
    started = time.monotonic()
    try:
        while True:
            snapshot = progress_snapshot(args.project, args.mode)
            completed = snapshot["completed"]
            now = time.monotonic()
            if baseline is None:
                baseline = completed
                previous = completed
            elif completed > previous:
                last_progress_at = now
            samples.append((now, completed))
            prune_rate_samples(samples, now, args.rate_window * 60.0)
            recent_rate = calculate_recent_rate(samples)
            elapsed = now - started
            last_progress_elapsed = (
                None if last_progress_at is None else now - last_progress_at
            )
            output = render_snapshot(
                snapshot,
                baseline,
                previous,
                elapsed,
                args.interval,
                recent_rate,
                args.rate_window,
                last_progress_elapsed,
            )
            if not args.no_clear and sys.stdout.isatty():
                sys.stdout.write("\033[2J\033[H")
            print(output, flush=True)
            if args.once:
                return 0
            previous = completed
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nMonitor detenido.")
        return 0
    except (OSError, RuntimeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
