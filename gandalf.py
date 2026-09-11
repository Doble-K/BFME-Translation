#!/usr/bin/env python3

import argparse
import contextlib
import io
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import uuid
from pathlib import Path

from tools.localization.extract import extract_str


ROOT = Path(__file__).resolve().parent
LOCALIZATION_TOOLS = ROOT / "tools" / "localization"
if str(LOCALIZATION_TOOLS) not in sys.path:
    sys.path.insert(0, str(LOCALIZATION_TOOLS))

from catalog_edit import CatalogEditError, commit_entry, search_entries
from opencode_farm import (
    farm_status,
    load_farm_config,
    load_farm_config_with_runtime_fallback,
)
from project import load_project, resolve_project_path


AUTO_ID_PREFIXES = ("LETTER:", "NUMBER:")
GANDALF_CONFIG_PATH = ROOT / "config" / "gandalf.local.json"
FARM_ACTIONS = {"start", "drain", "resume", "stop"}


def resolve_workspace_path(value):
    path = Path(value).expanduser()
    return (path if path.is_absolute() else ROOT / path).resolve()


def read_log_tail(path, line_count=200, chunk_size=8192, max_bytes=65536):
    path = Path(path)
    with path.open("rb") as log_file:
        log_file.seek(0, os.SEEK_END)
        position = log_file.tell()
        chunks = []
        newline_count = 0
        bytes_read = 0
        while (
            position > 0
            and newline_count <= line_count
            and bytes_read < max_bytes
        ):
            read_size = min(chunk_size, position, max_bytes - bytes_read)
            position -= read_size
            log_file.seek(position)
            chunk = log_file.read(read_size)
            chunks.append(chunk)
            newline_count += chunk.count(b"\n")
            bytes_read += read_size
    text = b"".join(reversed(chunks)).decode("utf-8", errors="replace")
    return "\n".join(text.splitlines()[-line_count:])


def start_gandalf_worker(work, callback, name):
    def worker():
        try:
            result = work()
            error = None
        except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as caught:
            result = None
            error = str(caught)
        callback(result, error)

    thread = threading.Thread(target=worker, name=name, daemon=True)
    thread.start()
    return thread


def gandalf_farm_command(action, config_path):
    if action not in FARM_ACTIONS:
        raise ValueError(f"acción de granja inválida: {action}")
    command = [
        sys.executable,
        str(ROOT / "tools/localization/opencode_farm.py"),
        action,
        "--config",
        str(resolve_workspace_path(config_path)),
    ]
    if action == "start":
        command.append("--detach")
    return command


def load_gandalf_config():
    if not GANDALF_CONFIG_PATH.exists():
        return {}
    try:
        with GANDALF_CONFIG_PATH.open(encoding="utf-8") as config_file:
            value = json.load(config_file)
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_gandalf_config(value):
    temporary_path = GANDALF_CONFIG_PATH.with_name(f".{GANDALF_CONFIG_PATH.name}.tmp")
    try:
        GANDALF_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with temporary_path.open("w", encoding="utf-8", newline="\n") as config_file:
            json.dump(value, config_file, ensure_ascii=False, indent=2)
            config_file.write("\n")
        os.replace(temporary_path, GANDALF_CONFIG_PATH)
    except OSError:
        if temporary_path.exists():
            temporary_path.unlink()
        raise


def greet():
    print("Bienvenido, viajero. Las puertas de Minas Tirith estan abiertas. - Gandalf")
    print("Gandalf preparara tu proyecto de localizacion.\n")


def ask(prompt, default=None):
    suffix = f" [{default}]" if default else ""
    value = input(f"{prompt}{suffix}: ").strip()
    return value or default


def choose_language(label, default):
    languages = {
        "1": ("es-419", "Español (Latinoamérica)"),
        "2": ("es-ES", "Español (Castellano)"),
        "3": ("en", "English"),
        "4": ("pr", "Português"),
        "5": ("fr", "Français"),
        "6": ("ge", "Deutsch"),
    }
    print(f"Idioma {label}:")
    for number, (code, name) in languages.items():
        print(f"  {number}. {code} - {name}")
    choice = ask("Selecciona una opcion", "1" if default == "es" else "3")
    if choice in languages:
        return languages[choice][0]
    raise ValueError("Idioma no disponible en modo basico; usa --advanced para un codigo personalizado")


def choose_project():
    print("Tipo de proyecto:")
    print("  1. BFME1")
    print("  2. BFME2")
    print("  3. BFME2 ROTWK 2.02")
    print("  4. Otro mod o juego SAGE")
    choice = ask("Selecciona una opcion", "3")
    presets = {
        "1": ("bfme1", "BFME1", "SAGE", None),
        "2": ("bfme2", "BFME2", "SAGE", None),
        "3": ("bfme2-rotwk-2.02", "BFME2 ROTWK 2.02", "SAGE", "2.02"),
    }
    if choice in presets:
        slug, name, engine, version = presets[choice]
        return {"slug": slug, "name": name, "engine": engine, "version": version}

    return {
        "slug": ask("Nombre corto del proyecto", "custom-sage-project"),
        "name": ask("Nombre del mod o juego", "Otro mod o juego SAGE"),
        "engine": ask("Motor", "SAGE"),
        "version": ask("Version", None),
    }


def find_big_files():
    candidates = []
    for directory in (ROOT / "source", ROOT / "sources"):
        if directory.exists():
            candidates.extend(path for path in directory.rglob("*.big") if path.is_file())
    return sorted(set(candidates))


def choose_big_file(project):
    candidates = find_big_files()
    if candidates:
        print("Archivos .big detectados:")
        for index, path in enumerate(candidates, 1):
            print(f"  {index}. {path.relative_to(ROOT)}")
        choice = ask("Selecciona un archivo o escribe una ruta", "1")
        if choice.isdigit() and 1 <= int(choice) <= len(candidates):
            return candidates[int(choice) - 1]
        selected = Path(choice).expanduser()
        return selected if selected.is_absolute() else ROOT / selected

    defaults = {
        "bfme1": "sources/bfme1.big",
        "bfme2": "sources/bfme2.big",
        "bfme2-rotwk-2.02": "sources/rotwk-2.02.big",
    }
    default = defaults.get(project["slug"], "sources/custom-sage.big")
    print("No se detecto ningun archivo .big en source/ ni sources/.")
    print("Coloca alli el .big original o escribe una ruta externa.")
    print(f"Ruta sugerida: {default}")
    selected = Path(ask("Ruta del archivo .big de origen", default)).expanduser()
    return selected if selected.is_absolute() else ROOT / selected


def inspect_big_file(big_file):
    binary = big4f_path()
    if not binary.exists():
        raise FileNotFoundError(f"No se encontro big4f en {binary}")
    if not big_file.exists():
        raise FileNotFoundError(f"No se encontro el archivo fuente {big_file}")
    result = subprocess.run(
        [str(binary), "l", str(big_file)],
        check=True,
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    string_files = [
        line.strip()
        for line in result.stdout.splitlines()
        if line.strip().lower().endswith(".str")
    ]
    if not string_files:
        raise ValueError(f"El archivo {big_file} no contiene archivos .str")
    print(f"big4f verifico el archivo. String files: {len(string_files)}")
    return string_files


def detect_language(big_file):
    name = big_file.name.lower()
    hints = (
        (("spanish", "espanol", "español"), "es-419"),
        (("castilian", "castellano"), "es-ES"),
        (("english", "ingles", "inglés"), "en"),
        (("portuguese", "portugues", "português"), "pr"),
        (("french", "frances", "français"), "fr"),
        (("german", "german", "deutsch"), "ge"),
    )
    for names, language in hints:
        if any(name_part in name for name_part in names):
            return language
    return None


def big4f_path():
    system = platform.system().lower()
    if "linux" in system:
        return ROOT / "tools/big4f/bin/linux/big4f"
    if "windows" in system:
        return ROOT / "tools/big4f/bin/windows/big4f.exe"
    if "darwin" in system:
        return ROOT / "tools/big4f/bin/macos/big4f"
    raise ValueError(f"Sistema no soportado: {system}")


def choose_string_file(extracted_root):
    files = sorted(path for path in extracted_root.rglob("*.str") if path.is_file())
    if not files:
        raise ValueError("El .big no contiene archivos .str")
    preferred = [path for path in files if path.as_posix().endswith("data/lotr.str")]
    files = preferred or files
    if len(files) == 1:
        return files[0]
    print("Archivos .str detectados:")
    for index, path in enumerate(files, 1):
        print(f"  {index}. {path.relative_to(extracted_root)}")
    choice = ask("Selecciona un archivo .str", "1")
    return files[int(choice) - 1]


def extract_source(big_file):
    binary = big4f_path()
    if not binary.exists():
        raise FileNotFoundError(f"No se encontro big4f en {binary}")
    if not big_file.exists():
        raise FileNotFoundError(f"No se encontro el archivo fuente {big_file}")

    temporary_directory = tempfile.TemporaryDirectory(prefix="gandalf-source-")
    extracted_root = Path(temporary_directory.name)
    subprocess.run(
        [str(binary), "x", str(big_file), str(extracted_root)],
        check=True,
        cwd=ROOT,
    )
    string_file = choose_string_file(extracted_root)
    entries = extract_str(string_file)
    return temporary_directory, string_file, entries


def create_catalog(data, output_path, settings):
    if output_path.exists() and not settings.get("force"):
        raise FileExistsError(
            f"El catálogo ya existe: {output_path}. Use otro nombre o --force."
        )

    result = {
        "source": data["source"],
        "language": settings["target_language"],
        "source_language": settings["source_language"],
        "target_language": settings["target_language"],
        "project": settings["project"],
        "source_archive": settings["source_archive"],
        "entries": [],
    }
    review_mode = settings.get("same_language_review", False)
    for entry in data["entries"]:
        current_text = entry["text"] if review_mode else ""
        automatic_id = entry["id"].startswith(AUTO_ID_PREFIXES)
        if automatic_id:
            current_text = entry["text"]
        result["entries"].append({
            "id": entry["id"],
            "source": entry["text"],
            "translation": current_text,
            "status": "preserved" if automatic_id else ("translated" if review_mode else "pending"),
            "line": entry["line"],
            "flags": (["system_preserved"] if automatic_id else (["needs_review"] if review_mode else [])),
            "notes": (
                "Entrada del sistema preservada; conservar salvo personalizacion intencional."
                if automatic_id
                else ""
            ),
            "translation_meta": {
                "origin": "system" if (review_mode or automatic_id) else None,
                "model": None,
                "date": None,
                "confidence": 1.0 if (review_mode or automatic_id) else 0.0,
            },
            "review": {
                "ai": {"checked": False, "issues": [], "last_review": None},
                "human": {"checked": False, "user": None, "date": None},
            },
            "history": ([{
                "date": None,
                "action": "auto_preserved" if automatic_id else "imported_for_review",
                "from": "",
                "to": current_text,
                "by": "system",
            }] if (review_mode or automatic_id) else []),
        })
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as output_file:
        json.dump(result, output_file, ensure_ascii=False, indent=2)
        output_file.write("\n")
    return len(result["entries"])


def create_project_config(config_path, settings, string_file):
    if config_path.exists() and not settings.get("force"):
        raise FileExistsError(
            f"La configuracion ya existe: {config_path}. Use otro nombre o --force."
        )
    target = settings["target_language"]
    project = settings["project"]
    config = {
        "name": project["slug"],
        "project": project,
        "source_archive": settings["source_archive"],
        "string_directory": f"translations/{target}",
        "string_files": [string_file],
        "catalog": settings["output_catalog"],
        "output_string_file": f"translations/{target}/{string_file}",
        "output_package": f"releases/{project['slug']}-{target}.big",
        "language": target,
        "encoding": settings["encoding"],
    }
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with config_path.open("w", encoding="utf-8", newline="\n") as config_file:
        json.dump(config, config_file, ensure_ascii=False, indent=2)
        config_file.write("\n")


def choose_model_cli():
    """Interactive CLI model selector. Returns ``(model_id, tier)``."""
    print("\nSelección de modelo de traducción:")
    tiers = list_models_by_tier()
    for tier in _TIER_ORDER:
        label = tier_label(tier)
        key = tier_menu_key(tier)
        count = len(tiers[tier])
        print(f"  {key}. {label} ({count} modelos)")
    choice = ask("Selecciona un tier", "1")
    tier_map = {str(i + 1): t for i, t in enumerate(_TIER_ORDER)}
    tier = tier_map.get(choice)
    if tier is None:
        raise ValueError("Selección de tier no válida")

    models = get_tier_models(tier)
    print(f"\nModelos en tier «{tier_label(tier)}»:")
    for index, model_id in enumerate(models, 1):
        print(f"  {index}. {model_id}")
    model_choice = ask("Selecciona un modelo", "1")
    if not model_choice.isdigit() or not (1 <= int(model_choice) <= len(models)):
        raise ValueError("Selección de modelo no válida")
    model_id = models[int(model_choice) - 1]

    if is_premium_tier(tier):
        registry = load_allowed_models()
        entry = registry["models"].get(model_id, {})
        if entry.get("require_confirmation"):
            print(f"\n⚠  El modelo {model_id} es premium y requiere confirmación explícita.")
            confirmation = ask("¿Confirmar uso del modelo premium? (s/N)", "n")
            if confirmation.lower() not in {"s", "si", "sí", "y", "yes"}:
                raise ValueError("Uso del modelo premium no confirmado")
            return select_model(tier, model_id, confirmed=True)

    return select_model(tier, model_id)


def handoff_to_translation(output_path, config_path, settings, advanced):
    print("\nSiguiente paso:")
    print("  1. Iniciar batch manual")
    print("  2. Preparar lote pequeño para un agente externo")
    print("  3. Ver batch manual sin modificar")
    print("  4. Salir")
    choice = ask("Selecciona una opcion", "1")
    if choice == "4":
        return

    count_value = ask("Cantidad de entradas", "20")
    try:
        count = int(count_value)
        if count < 1:
            raise ValueError
    except ValueError as error:
        raise ValueError("La cantidad debe ser un entero mayor que cero") from error

    if choice == "2":
        command = [
            sys.executable,
            str(ROOT / "tools/localization/agent_batch.py"),
            "export",
            "--project",
            str(config_path),
            "--count",
            str(count),
            "--mode",
            "incomplete",
            "--worker",
            "gandalf-cli",
        ]
        subprocess.run(command, cwd=ROOT, check=True)
        return

    command = [
        sys.executable,
        str(ROOT / "tools/localization/translate.py"),
        str(output_path),
        "--count",
        str(count),
        "--project",
        str(config_path),
    ]
    if choice == "1":
        command.append("--edit")
    if settings.get("same_language_review"):
        command.append("--review")
    if advanced:
        command.append("--advanced")
    subprocess.run(command, cwd=ROOT, check=True)


def wizard(
    force=False,
    allow_same_language=False,
    advanced=False,
    source_language_override=None,
    target_language_override=None,
):
    greet()
    project = choose_project()
    big_file = choose_big_file(project)
    inspect_big_file(big_file)
    detected_language = detect_language(big_file)
    if detected_language:
        print(f"Idioma detectado por el nombre del archivo: {detected_language}")
    else:
        print("No se pudo detectar el idioma del archivo; selecciona uno manualmente.")

    if source_language_override:
        source_language = source_language_override
    elif advanced:
        source_language = ask("Idioma de origen", detected_language or "en-US")
    else:
        source_language = choose_language("de origen", detected_language or "en")

    if target_language_override:
        target_language = target_language_override
    elif advanced:
        target_language = ask("Idioma de destino", "es-419")
    else:
        target_language = choose_language("de destino", "es-419")
    if (
        not allow_same_language
        and source_language.split("-")[0].lower()
        == target_language.split("-")[0].lower()
    ):
        confirmation = ask(
            f"Origen y destino parecen iguales ({source_language} -> {target_language}). "
            "¿Es una revision intencional? (s/N)",
            "n",
        )
        if confirmation.lower() not in {"s", "si", "sí", "y", "yes"}:
            raise ValueError("Operacion cancelada: idiomas iguales sin confirmacion")
    encoding = ask("Encoding SAGE", "cp1252")
    model_id, model_tier = choose_model_cli()
    slug = project["slug"]
    output_path = Path(ask(
        "Catalogo de trabajo de salida",
        f"catalogs/{slug}_{target_language}_work.json",
    ))
    config_path = Path(ask(
        "Configuracion de proyecto de salida",
        f"config/{slug}_{target_language}.json",
    ))
    source_archive = str(big_file)
    try:
        source_archive = str(big_file.resolve().relative_to(ROOT))
    except ValueError:
        pass
    settings = {
        "project": project,
        "source_language": source_language,
        "target_language": target_language,
        "source_archive": source_archive,
        "output_catalog": str(output_path),
        "encoding": encoding,
        "force": force,
        "model": model_id,
        "model_tier": model_tier,
        "same_language_review": source_language.split("-")[0].lower()
        == target_language.split("-")[0].lower(),
    }
    if not force and (output_path.exists() or config_path.exists()):
        if output_path.exists():
            print("El catalogo de salida ya existe.")
            print("  1. Usar el catalogo existente")
            print("  2. Reemplazar catalogo y configuracion")
            print("  3. Salir")
            choice = ask("Selecciona una opcion", "1")
            if choice == "1":
                print(f"Usando catalogo existente: {output_path}")
                handoff_to_translation(output_path, config_path, settings, advanced)
                return
            if choice != "2":
                raise ValueError("Operacion cancelada: archivos de salida conservados")
        else:
            confirmation = ask("¿Deseas reemplazar la configuracion existente? (s/N)", "n")
            if confirmation.lower() not in {"s", "si", "sí", "y", "yes"}:
                raise ValueError("Operacion cancelada: archivos de salida conservados")
        force = True
        settings["force"] = True
    temporary_directory, string_file, entries = extract_source(big_file)
    try:
        relative_string_file = string_file.relative_to(Path(temporary_directory.name)).as_posix()
        source_data = {"source": relative_string_file, "entries": entries}
        count = create_catalog(source_data, output_path, settings)
        create_project_config(config_path, settings, relative_string_file)
    finally:
        temporary_directory.cleanup()
    print(f"Catalogo creado: {output_path}")
    print(f"Entradas: {count}")
    print(f"Proyecto: {project['name']}")
    print(f"Idioma: {source_language} -> {target_language}")
    print(f"Modelo: {model_id} ({tier_label(model_tier)})")
    print(f"Configuracion: {config_path}")
    handoff_to_translation(output_path, config_path, settings, advanced)


def non_interactive(args):
    if not args.input or not args.output:
        raise ValueError("indique input y output, o ejecute Gandalf sin argumentos")
    source_path = Path(args.input)
    output_path = Path(args.output)
    if output_path.exists() and not args.force:
        raise FileExistsError(
            f"El catalogo ya existe: {output_path}. Use --force solo explicitamente."
        )
    with source_path.open(encoding="utf-8") as source_file:
        data = json.load(source_file)
    settings = {
        "project": {"slug": "custom", "name": "Custom project", "engine": "SAGE", "version": None},
        "source_language": "unknown",
        "target_language": "Spanish",
        "source_archive": None,
        "output_catalog": str(output_path),
        "encoding": "cp1252",
        "force": args.force,
    }
    return create_catalog(data, output_path, settings)


def farm_button_states(
    active,
    mode,
    enabled=True,
    control_supported=True,
    project_changed=False,
    profile_available=True,
    action_running=False,
):
    if not enabled or action_running:
        return ("disabled",) * 4
    return (
        "normal" if not active and profile_available else "disabled",
        "normal"
        if active
        and mode == "running"
        and control_supported
        and not project_changed
        and profile_available
        else "disabled",
        "normal"
        if (not active or mode == "draining")
        and control_supported
        and not project_changed
        and profile_available
        else "disabled",
        "normal" if active else "disabled",
    )


def format_entry_header(record):
    """Build the contextual header line for a catalog entry view.

    UI-agnostic helper used by the translation/debug window: returns the
    entry id, status, flags and, when the entry is reserved, the list of
    workers holding the reservation.  Covered by unit tests that do not
    require a display.
    """
    flags = ", ".join(record.get("flags") or []) or "sin flags"
    header = f"{record['id']} | estado={record['status']} | {flags}"
    reservations = record.get("reservations") or []
    if record.get("reserved") and reservations:
        workers = ", ".join(
            item.get("worker") or "desconocido" for item in reservations
        )
        header += f" | RESERVADA por {workers}"
    return header


def translation_pane_labels(source_language, target_language):
    """Return the side-by-side pane titles for the A/B translation window."""
    return (
        f"Idioma A - origen ({source_language})",
        f"Idioma B - destino ({target_language})",
    )


def launch_gui():
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk
    except ImportError as error:
        raise RuntimeError("La GUI requiere tkinter instalado en Python") from error

    try:
        root = tk.Tk()
    except tk.TclError as error:
        raise RuntimeError("No se pudo iniciar la GUI; comprueba que haya un display disponible") from error
    root.title("Gandalf - SAGE Localization")
    root.geometry("900x720")
    root.minsize(780, 620)

    def add_tooltip(widget, text):
        tooltip_window = None
        scheduled = None

        def hide(_event=None):
            nonlocal tooltip_window, scheduled
            if scheduled:
                root.after_cancel(scheduled)
                scheduled = None
            if tooltip_window is not None:
                tooltip_window.destroy()
                tooltip_window = None

        def show(_event=None):
            nonlocal tooltip_window, scheduled
            hide()

            def create():
                nonlocal tooltip_window
                if not widget.winfo_exists():
                    return
                tooltip_window = tk.Toplevel(root)
                tooltip_window.overrideredirect(True)
                tooltip_window.attributes("-topmost", True)
                label = tk.Label(
                    tooltip_window,
                    text=text,
                    justify="left",
                    padx=8,
                    pady=5,
                    bg="#003B00" if dark_mode_var.get() else "#fff8dc",
                    fg="#00FF41" if dark_mode_var.get() else "#20242b",
                )
                label.pack()
                x = widget.winfo_rootx()
                y = widget.winfo_rooty() + widget.winfo_height() + 4
                tooltip_window.geometry(f"+{x}+{y}")

            scheduled = root.after(650, create)

        widget.bind("<Enter>", show, add="+")
        widget.bind("<Leave>", hide, add="+")
        widget.bind("<ButtonPress>", hide, add="+")

    project_presets = {
        "BFME1": {"slug": "bfme1", "name": "BFME1", "engine": "SAGE", "version": None},
        "BFME2": {"slug": "bfme2", "name": "BFME2", "engine": "SAGE", "version": None},
        "BFME2 ROTWK 2.02": {
            "slug": "bfme2-rotwk-2.02",
            "name": "BFME2 ROTWK 2.02",
            "engine": "SAGE",
            "version": "2.02",
        },
        "Otro mod SAGE": {
            "slug": "custom-sage-project",
            "name": "Otro mod o juego SAGE",
            "engine": "SAGE",
            "version": None,
        },
    }
    languages = {
        "Español (Latinoamérica)": "es-419",
        "Español (Castellano)": "es-ES",
        "English": "en",
        "Português": "pr",
        "Français": "fr",
        "Deutsch": "ge",
    }
    candidates = find_big_files()
    saved_config = load_gandalf_config()
    saved_last = saved_config.get("last", {}) if isinstance(saved_config.get("last", {}), dict) else {}
    project_var = tk.StringVar(value=saved_last.get("project", "BFME2 ROTWK 2.02"))
    source_var = tk.StringVar(value=saved_last.get("source", str(candidates[0] if candidates else ROOT / "sources/englishpatch202.big")))
    source_language_var = tk.StringVar(value=saved_last.get("source_language", "English"))
    target_language_var = tk.StringVar(value=saved_last.get("target_language", "Español (Latinoamérica)"))
    encoding_var = tk.StringVar(value=saved_last.get("encoding", "cp1252"))
    catalog_var = tk.StringVar(value=saved_last.get("catalog", "catalogs/bfme2-rotwk-2.02_es_work.json"))
    config_var = tk.StringVar(value=saved_last.get("config", "config/bfme2-rotwk-2.02_es.json"))
    farm_config_var = tk.StringVar(
        value=saved_last.get("farm_config", "config/opencode_farm.json")
    )
    tier_var = tk.StringVar(value=saved_last.get("model_tier", "free"))
    model_var = tk.StringVar(value=saved_last.get("model", ""))
    premium_confirmed_var = tk.BooleanVar(value=False)
    model_status_var = tk.StringVar(value="Selecciona un tier y modelo.")
    force_var = tk.BooleanVar(value=False)
    dark_mode_var = tk.BooleanVar(value=False)
    run_mode_var = tk.StringVar(value=saved_last.get("mode", "Agente externo"))
    run_count_var = tk.StringVar(value=saved_last.get("count", "20"))
    status_var = tk.StringVar(value="Listo para preparar un proyecto.")
    farm_status_var = tk.StringVar(value="Granja: comprobando estado...")
    process_handle = None
    worker_thread = None
    process_paused = False
    close_when_done = False
    farm_action_running = False
    farm_status_refresh_running = False
    farm_status_after_id = None

    style = ttk.Style(root)
    style.theme_use("clam")
    frame = ttk.Frame(root, padding=20)
    frame.pack(fill="both", expand=True)

    topbar = ttk.Frame(frame)
    topbar.pack(fill="x")
    ttk.Label(topbar, text="Gandalf", font=("TkDefaultFont", 22, "bold")).pack(side="left")
    ttk.Checkbutton(topbar, text="Modo oscuro", variable=dark_mode_var).pack(side="right")
    ttk.Label(
        frame,
        text="Prepara un proyecto de localización SAGE sin salir de la Tierra Media.",
    ).pack(anchor="w", pady=(0, 16))

    form = ttk.Frame(frame)
    form.pack(fill="x")
    input_widgets = []

    def add_row(label, variable, values=None, browse=False):
        row = ttk.Frame(form)
        row.pack(fill="x", pady=4)
        ttk.Label(row, text=label, width=22).pack(side="left")
        if values is None:
            widget = ttk.Entry(row, textvariable=variable)
            widget.pack(side="left", fill="x", expand=True)
        else:
            widget = ttk.Combobox(row, textvariable=variable, values=values, state="readonly")
            widget.pack(side="left", fill="x", expand=True)
        input_widgets.append(widget)
        if browse:
            ttk.Button(row, text="Examinar", command=lambda: browse_source()).pack(side="left", padx=(8, 0))
        return widget

    add_row("Proyecto", project_var, list(project_presets))
    add_row("Archivo .big", source_var, browse=True)
    add_row("Idioma de origen", source_language_var, list(languages))
    add_row("Idioma de destino", target_language_var, list(languages))
    add_row("Encoding SAGE", encoding_var)
    add_row("Catálogo de salida", catalog_var)
    add_row("Configuración de salida", config_var)
    add_row("Perfil de granja", farm_config_var)

    model_frame = ttk.LabelFrame(form, text="Modelo de traducción")
    model_frame.pack(fill="x", pady=(8, 0))
    model_row_tier = ttk.Frame(model_frame)
    model_row_tier.pack(fill="x", padx=8, pady=(8, 4))
    ttk.Label(model_row_tier, text="Tier", width=22).pack(side="left")
    tier_values = [tier_label(t) for t in _TIER_ORDER]
    tier_combobox = ttk.Combobox(
        model_row_tier,
        textvariable=tier_var,
        values=tier_values,
        state="readonly",
    )
    tier_combobox.pack(side="left", fill="x", expand=True)
    input_widgets.append(tier_combobox)

    model_row_model = ttk.Frame(model_frame)
    model_row_model.pack(fill="x", padx=8, pady=4)
    ttk.Label(model_row_model, text="Modelo", width=22).pack(side="left")
    model_combobox = ttk.Combobox(
        model_row_model,
        textvariable=model_var,
        state="readonly",
    )
    model_combobox.pack(side="left", fill="x", expand=True)
    input_widgets.append(model_combobox)

    model_row_confirm = ttk.Frame(model_frame)
    model_row_confirm.pack(fill="x", padx=8, pady=(4, 4))
    premium_confirm_check = ttk.Checkbutton(
        model_row_confirm,
        text="Confirmo uso de modelo premium (requiere confirmación explícita)",
        variable=premium_confirmed_var,
    )
    premium_confirm_check.pack(side="left")
    input_widgets.append(premium_confirm_check)

    model_row_status = ttk.Frame(model_frame)
    model_row_status.pack(fill="x", padx=8, pady=(0, 8))
    ttk.Label(model_row_status, textvariable=model_status_var, wraplength=600).pack(side="left")

    def refresh_model_list(*_):
        """Update the model combobox when the tier changes."""
        tier_label_text = tier_var.get()
        tier_key = None
        for t in _TIER_ORDER:
            if tier_label(t) == tier_label_text:
                tier_key = t
                break
        if tier_key is None:
            model_combobox.configure(values=[])
            model_var.set("")
            model_status_var.set("Tier no válido.")
            return
        models = get_tier_models(tier_key)
        model_combobox.configure(values=models)
        if model_var.get() not in models:
            model_var.set(models[0] if models else "")
        _update_model_status()
        premium_confirm_check.configure(
            state="normal" if is_premium_tier(tier_key) else "disabled"
        )
        if not is_premium_tier(tier_key):
            premium_confirmed_var.set(False)

    def _update_model_status(*_):
        """Refresh the model status label."""
        tier_label_text = tier_var.get()
        tier_key = None
        for t in _TIER_ORDER:
            if tier_label(t) == tier_label_text:
                tier_key = t
                break
        if tier_key is None or not model_var.get():
            model_status_var.set("Selecciona un tier y modelo.")
            return
        model_status_var.set(format_model_status(tier_key, model_var.get()))

    tier_var.trace_add("write", refresh_model_list)
    model_var.trace_add("write", _update_model_status)
    refresh_model_list()

    ttk.Checkbutton(form, text="Reemplazar archivos existentes", variable=force_var).pack(anchor="w", pady=8)

    run_frame = ttk.LabelFrame(frame, text="Ejecutar traducción")
    run_frame.pack(fill="x", pady=(8, 0))
    run_controls = ttk.Frame(run_frame)
    run_controls.pack(fill="x", padx=8, pady=8)
    ttk.Label(run_controls, text="Modo").pack(side="left")
    ttk.Combobox(
        run_controls,
        textvariable=run_mode_var,
        values=("Agente externo", "Manual (terminal)"),
        state="readonly",
        width=18,
    ).pack(side="left", padx=(6, 12))
    ttk.Label(run_controls, text="Entradas").pack(side="left")
    ttk.Entry(run_controls, textvariable=run_count_var, width=7).pack(side="left", padx=(6, 12))

    progress_frame = ttk.LabelFrame(frame, text="Progreso del lote")
    progress_frame.pack(fill="both", expand=True)
    progress_bar = ttk.Progressbar(progress_frame, mode="determinate", maximum=1, value=0)
    progress_bar.pack(fill="x", padx=8, pady=(8, 4))
    completed_controls = ttk.Frame(progress_frame)
    completed_controls.pack(fill="x", padx=8, pady=(0, 4))
    ttk.Label(completed_controls, text="Resultados completados:").pack(side="left")
    completed_var = tk.StringVar()
    completed_selector = ttk.Combobox(
        completed_controls,
        textvariable=completed_var,
        state="readonly",
        width=58,
    )
    completed_selector.pack(side="left", fill="x", expand=True, padx=(8, 0))
    language_frame = ttk.Frame(progress_frame)
    language_frame.pack(fill="both", expand=True, padx=8, pady=(4, 8))
    source_frame = ttk.LabelFrame(language_frame, text="Idioma A - origen")
    source_frame.pack(side="left", fill="both", expand=True, padx=(0, 4))
    target_frame = ttk.LabelFrame(language_frame, text="Idioma B - traducción")
    target_frame.pack(side="left", fill="both", expand=True, padx=(4, 0))
    source_view = tk.Text(source_frame, height=8, state="disabled", wrap="word")
    source_view.pack(fill="both", expand=True, padx=6, pady=6)
    target_view = tk.Text(target_frame, height=8, state="disabled", wrap="word")
    target_view.pack(fill="both", expand=True, padx=6, pady=6)
    debug_lines = []
    debug_window = None
    debug_view = None
    completed_ids = []
    completed_records = {}
    translation_view_window = None
    translation_view_widgets = []

    def apply_theme(*_):
        dark = dark_mode_var.get()
        colors = {
            "background": "#0D0208" if dark else "#f3f4f6",
            "surface": "#003B00" if dark else "#ffffff",
            "foreground": "#00FF41" if dark else "#20242b",
            "muted": "#008F11" if dark else "#4b5563",
            "accent": "#00FF41" if dark else "#7b5b2e",
        }
        root.configure(bg=colors["background"])
        style.configure("TFrame", background=colors["background"])
        style.configure("TLabel", background=colors["background"], foreground=colors["foreground"])
        style.configure("TCheckbutton", background=colors["background"], foreground=colors["foreground"])
        style.configure("TLabelframe", background=colors["background"], foreground=colors["foreground"])
        style.configure("TLabelframe.Label", background=colors["background"], foreground=colors["foreground"])
        style.map("TCheckbutton", background=[("active", colors["background"])])
        style.configure(
            "TButton",
            background=colors["surface"],
            foreground=colors["foreground"],
            bordercolor=colors["accent"],
            lightcolor=colors["surface"],
            darkcolor=colors["surface"],
        )
        style.map("TButton", background=[("active", colors["accent"])])
        style.configure(
            "TEntry",
            fieldbackground=colors["surface"],
            foreground=colors["foreground"],
            insertcolor=colors["foreground"],
        )
        style.configure(
            "TCombobox",
            fieldbackground=colors["surface"],
            background=colors["surface"],
            foreground=colors["foreground"],
            arrowcolor=colors["accent"],
        )
        style.map("TCombobox", fieldbackground=[("readonly", colors["surface"])])
        for text_widget in (
            (source_view, target_view, debug_view)
            + tuple(translation_view_widgets)
        ):
            if text_widget is not None:
                text_widget.configure(
                    background=colors["surface"],
                    foreground=colors["foreground"],
                    insertbackground=colors["foreground"],
                    selectbackground=colors["accent"],
                )

    dark_mode_var.trace_add("write", apply_theme)
    apply_theme()

    def write_output(text):
        debug_lines.append(text)
        if debug_view is not None and debug_view.winfo_exists():
            debug_view.configure(state="normal")
            debug_view.insert("end", text)
            debug_view.see("end")
            debug_view.configure(state="disabled")

    def write_progress(text):
        status_var.set(text.rstrip().split("\n")[-1])

    def set_text(widget, text):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("end", text)
        widget.configure(state="disabled")

    def persist_settings():
        try:
            save_gandalf_config({
                "last": {
                    "project": project_var.get(),
                    "source": source_var.get(),
                    "source_language": source_language_var.get(),
                    "target_language": target_language_var.get(),
                    "encoding": encoding_var.get(),
                    "catalog": catalog_var.get(),
                    "config": config_var.get(),
                    "farm_config": farm_config_var.get(),
                    "model_tier": tier_var.get(),
                    "model": model_var.get(),
                    "mode": run_mode_var.get(),
                    "count": run_count_var.get(),
                },
            })
        except (OSError, ValueError):
            status_var.set("No se pudo guardar la configuración local.")

    def show_completed(*_):
        record = completed_records.get(completed_var.get())
        if record:
            set_text(source_view, record["source"])
            set_text(target_view, record["translation"])
            status_var.set(f"Revisión: {record['id']} ({record['model']})")

    completed_selector.bind("<<ComboboxSelected>>", show_completed)

    def open_debug_window():
        nonlocal debug_window, debug_view
        if debug_window is not None and debug_window.winfo_exists():
            debug_window.deiconify()
            debug_window.lift()
            return
        debug_window = tk.Toplevel(root)
        debug_window.title("Gandalf - Debug")
        debug_window.geometry("900x520")
        debug_view = tk.Text(debug_window, state="disabled", wrap="none")
        debug_view.pack(fill="both", expand=True, padx=8, pady=8)
        if debug_lines:
            debug_view.configure(state="normal")
            debug_view.insert("end", "".join(debug_lines))
            debug_view.configure(state="disabled")
        apply_theme()

        def close_debug():
            nonlocal debug_window, debug_view
            debug_window.destroy()
            debug_window = None
            debug_view = None

        debug_window.protocol("WM_DELETE_WINDOW", close_debug)

    def handle_process_line(text):
        write_output(text if text.endswith("\n") else f"{text}\n")
        entry_match = re.match(r"ENTRY (\{.*\})$", text)
        if entry_match:
            try:
                entry = json.loads(entry_match.group(1))
                source = entry.get("source", "")
                if not completed_records:
                    set_text(source_view, source)
                    set_text(target_view, "Procesando...")
                status_var.set(f"{entry['current']}/{entry['total']}  {entry['id']}  ({entry['model']})")
            except (json.JSONDecodeError, KeyError, TypeError):
                write_progress("No se pudo interpretar el evento de entrada; revisa Debug.")
        result_match = re.match(r"RESULT (\{.*\})$", text)
        if result_match:
            try:
                result = json.loads(result_match.group(1))
                result_id = result["id"]
                if result_id not in completed_records:
                    completed_ids.append(result_id)
                completed_records[result_id] = result
                completed_selector.configure(values=completed_ids)
                completed_var.set(result_id)
                set_text(source_view, result["source"])
                set_text(target_view, result["translation"])
                status_var.set(f"{result['current']}/{result['total']}  OK  {result_id}")
            except (json.JSONDecodeError, KeyError, TypeError):
                write_progress("No se pudo interpretar el resultado; revisa Debug.")
        batch_match = re.search(r"\bBATCH\s+(\d+)", text)
        if batch_match:
            progress_bar.configure(maximum=int(batch_match.group(1)), value=0)
            status_var.set(f"Lote iniciado: {batch_match.group(1)} entradas")
        progress_match = re.search(r"\bPROGRESS\s+(\d+)/(\d+)\s+(OK|SKIP)\s+(.+)", text)
        if progress_match:
            current, total, result, details = progress_match.groups()
            progress_bar.configure(maximum=int(total), value=int(current))
            status_var.set(f"Resultado: {result}  {details}")

    def log_line(text):
        root.after(0, lambda: handle_process_line(text.rstrip("\n")))

    def browse_source():
        selected = filedialog.askopenfilename(
            title="Selecciona el archivo .big de origen",
            filetypes=[("SAGE BIG", "*.big"), ("Todos los archivos", "*")],
        )
        if selected:
            source_var.set(selected)

    def update_defaults(*_):
        project = project_presets[project_var.get()]
        target = languages[target_language_var.get()]
        catalog_var.set(f"catalogs/{project['slug']}_{target}_work.json")
        config_var.set(f"config/{project['slug']}_{target}.json")

    project_var.trace_add("write", update_defaults)
    target_language_var.trace_add("write", update_defaults)

    def create_project():
        persist_settings()
        project = project_presets[project_var.get()].copy()
        source_path = Path(source_var.get()).expanduser()
        output_path = Path(catalog_var.get()).expanduser()
        config_path = Path(config_var.get()).expanduser()
        source_language = languages[source_language_var.get()]
        target_language = languages[target_language_var.get()]
        settings = {
            "project": project,
            "source_language": source_language,
            "target_language": target_language,
            "source_archive": str(source_path),
            "output_catalog": str(output_path),
            "encoding": encoding_var.get().strip() or "cp1252",
            "force": force_var.get(),
            "same_language_review": source_language == target_language,
        }

        tier_label_text = tier_var.get()
        tier_key = None
        for t in _TIER_ORDER:
            if tier_label(t) == tier_label_text:
                tier_key = t
                break
        if tier_key is None or not model_var.get():
            messagebox.showerror("Modelo no seleccionado", "Selecciona un tier y modelo de traducción.")
            return
        try:
            model_id, model_tier = select_model(
                tier_key, model_var.get(), confirmed=premium_confirmed_var.get()
            )
        except ValueError as error:
            messagebox.showerror("Modelo inválido", str(error))
            return
        settings["model"] = model_id
        settings["model_tier"] = model_tier

        def worker():
            try:
                if not settings["force"] and (output_path.exists() or config_path.exists()):
                    raise FileExistsError("Ya existe el catálogo o la configuración; activa reemplazo para continuar.")
                captured = io.StringIO()
                with contextlib.redirect_stdout(captured):
                    temporary_directory, string_file, entries = extract_source(source_path)
                    try:
                        relative_string_file = string_file.relative_to(Path(temporary_directory.name)).as_posix()
                        count = create_catalog(
                            {"source": relative_string_file, "entries": entries}, output_path, settings
                        )
                        create_project_config(config_path, settings, relative_string_file)
                    finally:
                        temporary_directory.cleanup()
                message = (
                    f"Proyecto creado correctamente.\nCatálogo: {output_path}\n"
                    f"Configuración: {config_path}\nEntradas: {count}\n\n{captured.getvalue()}"
                )
                root.after(0, finish, message, True)
            except (OSError, ValueError, subprocess.CalledProcessError) as error:
                message = f"Error: {error}\n"
                root.after(0, finish, message, False)

        status_var.set("Extrayendo y preparando el catálogo...")
        create_button.configure(state="disabled")
        run_button.configure(state="disabled")
        build_button.configure(state="disabled")
        correct_button.configure(state="disabled")
        for widget in input_widgets:
            widget.configure(state="disabled")
        threading.Thread(target=worker, daemon=True).start()

    def finish(message, success):
        write_output(message)
        status_var.set("Proyecto listo." if success else "La operación terminó con errores.")
        create_button.configure(state="normal")
        run_button.configure(state="normal")
        build_button.configure(state="normal")
        correct_button.configure(state="normal")
        for widget in input_widgets:
            widget.configure(state="readonly" if isinstance(widget, ttk.Combobox) else "normal")
        if success:
            messagebox.showinfo("Gandalf", "El catálogo y la configuración fueron creados.")

    def open_manual_terminal(catalog_path, config_path, count):
        command = [
            sys.executable,
            str(ROOT / "tools/localization/translate.py"),
            "--project",
            str(config_path),
            "--count",
            str(count),
            "--edit",
        ]
        terminals = [
            ("x-terminal-emulator", ["-e"]),
            ("konsole", ["-e"]),
            ("gnome-terminal", ["--"]),
            ("kitty", []),
            ("alacritty", ["-e"]),
        ]
        for terminal, prefix in terminals:
            if shutil.which(terminal):
                subprocess.Popen([terminal, *prefix, *command], cwd=ROOT)
                write_output("Editor manual abierto en una terminal.\n")
                return
        raise RuntimeError("No se encontró una terminal gráfica compatible para el modo manual.")

    def run_translation():
        persist_settings()
        try:
            count = int(run_count_var.get())
            if not 1 <= count <= 100:
                raise ValueError
        except ValueError as error:
            messagebox.showerror("Valores inválidos", "Entradas debe estar entre 1 y 100.")
            return

        tier_label_text = tier_var.get()
        tier_key = None
        for t in _TIER_ORDER:
            if tier_label(t) == tier_label_text:
                tier_key = t
                break
        if tier_key is None or not model_var.get():
            messagebox.showerror("Modelo no seleccionado", "Selecciona un tier y modelo de traducción.")
            return
        try:
            select_model(tier_key, model_var.get(), confirmed=premium_confirmed_var.get())
        except ValueError as error:
            messagebox.showerror("Modelo inválido", str(error))
            return

        config_path = Path(config_var.get()).expanduser()
        if not config_path.exists():
            messagebox.showerror("Proyecto no encontrado", "Prepara el proyecto o indica una configuración existente.")
            return
        if run_mode_var.get() == "Manual (terminal)":
            try:
                open_manual_terminal(Path(catalog_var.get()), config_path, count)
            except (OSError, RuntimeError) as error:
                write_output(f"Error: {error}\n")
            return

        command = [
            sys.executable,
            str(ROOT / "tools/localization/agent_batch.py"),
            "export",
            "--project",
            str(config_path),
            "--count",
            str(count),
            "--mode",
            "incomplete",
            "--worker",
            "gandalf-gui",
        ]
        try:
            result = subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True)
            write_output(f"$ {' '.join(command)}\n{result.stdout}")
            batch_match = re.search(r"^BATCH_FILE (.+)$", result.stdout, re.MULTILINE)
            response_match = re.search(r"^RESPONSE_FILE (.+)$", result.stdout, re.MULTILINE)
            if not batch_match or not response_match:
                raise ValueError("La herramienta no informó las rutas del lote y la respuesta")
            batch_path = Path(batch_match.group(1))
            response_path = Path(response_match.group(1))
            batch = json.loads(batch_path.read_text(encoding="utf-8"))
            progress_bar.configure(maximum=max(1, len(batch["entries"])), value=0)
            set_text(source_view, f"Lote exportado con {len(batch['entries'])} entradas.")
            set_text(target_view, f"Batch: {batch_path}\nRespuesta: {response_path}")
            status_var.set("Lote listo para un agente externo.")
            messagebox.showinfo(
                "Lote para agente",
                f"Batch de solo lectura:\n{batch_path}\n\n"
                f"Respuesta editable:\n{response_path}\n\n"
                "El agente debe completar la respuesta y ejecutar agent_batch.py apply.",
            )
        except (OSError, ValueError, subprocess.CalledProcessError, json.JSONDecodeError, KeyError) as error:
            write_output(f"Error: {error}\n")
            status_var.set("No se pudo preparar el lote para el agente.")

    def run_finished(return_code):
        nonlocal process_handle, worker_thread, process_paused, close_when_done
        process_handle = None
        worker_thread = None
        process_paused = False
        run_button.configure(state="normal")
        create_button.configure(state="normal")
        build_button.configure(state="normal")
        correct_button.configure(state="normal")
        for widget in input_widgets:
            widget.configure(state="readonly" if isinstance(widget, ttk.Combobox) else "normal")
        status_var.set("Ejecución terminada." if return_code == 0 else "Ejecución terminada con errores.")
        pause_button.configure(state="disabled")
        if close_when_done:
            root.after(250, root.destroy)

    def build_test_package():
        nonlocal process_handle, worker_thread
        persist_settings()
        config_path = Path(config_var.get()).expanduser()
        if not config_path.exists():
            messagebox.showerror("Proyecto no encontrado", "Prepara el proyecto antes de construir.")
            return
        commands = [
            [
                sys.executable,
                str(ROOT / "tools/localization/build.py"),
                "--project",
                str(config_path),
                "--allow-source-fallback",
            ],
            [
                sys.executable,
                str(ROOT / "tools/localization/pack.py"),
                "--project",
                str(config_path),
            ],
        ]
        write_output("$ build --allow-source-fallback && pack\n")
        build_button.configure(state="disabled")
        run_button.configure(state="disabled")
        create_button.configure(state="disabled")
        correct_button.configure(state="disabled")
        status_var.set("Construyendo paquete de prueba...")

        def worker():
            nonlocal process_handle
            try:
                return_code = 0
                for command in commands:
                    write_output(f"$ {' '.join(command)}\n")
                    process = subprocess.Popen(
                        command,
                        cwd=ROOT,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        bufsize=1,
                    )
                    process_handle = process
                    for line in process.stdout:
                        log_line(line)
                    return_code = process.wait()
                    if return_code:
                        break
                root.after(0, run_finished, return_code)
            except OSError as error:
                log_line(f"Error: {error}")
                root.after(0, run_finished, 1)

        worker_thread = threading.Thread(target=worker, name="gandalf-build", daemon=False)
        worker_thread.start()

    def open_catalog_editor():
        config_path = Path(config_var.get()).expanduser()
        if not config_path.exists():
            messagebox.showerror(
                "Proyecto no encontrado",
                "Prepara el proyecto o indica una configuración existente.",
            )
            return

        editor = tk.Toplevel(root)
        editor.title("Gandalf - Corregir traducciones")
        editor.geometry("1040x680")
        editor.minsize(820, 540)
        container = ttk.Frame(editor, padding=12)
        container.pack(fill="both", expand=True)

        search_frame = ttk.Frame(container)
        search_frame.pack(fill="x", pady=(0, 8))
        query_var = tk.StringVar()
        filter_var = tk.StringVar(value="Todas")
        editor_status_var = tk.StringVar(value="Cargando entradas...")
        ttk.Label(search_frame, text="Buscar").pack(side="left")
        query_entry = ttk.Entry(search_frame, textvariable=query_var)
        query_entry.pack(side="left", fill="x", expand=True, padx=(6, 8))
        ttk.Combobox(
            search_frame,
            textvariable=filter_var,
            values=(
                "Todas",
                "Pendientes",
                "Traducidas",
                "Por revisar",
                "Revisadas",
                "Preservadas",
            ),
            state="readonly",
            width=14,
        ).pack(side="left")

        content = ttk.Panedwindow(container, orient="horizontal")
        content.pack(fill="both", expand=True)
        results_frame = ttk.LabelFrame(content, text="Entradas")
        details_frame = ttk.Frame(content)
        content.add(results_frame, weight=2)
        content.add(details_frame, weight=3)

        result_list = tk.Listbox(results_frame, exportselection=False)
        result_scroll = ttk.Scrollbar(
            results_frame, orient="vertical", command=result_list.yview
        )
        result_list.configure(yscrollcommand=result_scroll.set)
        result_list.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=6)
        result_scroll.pack(side="right", fill="y", padx=(0, 6), pady=6)

        info_var = tk.StringVar(value="Selecciona una entrada.")
        ttk.Label(details_frame, textvariable=info_var, wraplength=560).pack(
            anchor="w", fill="x", pady=(0, 6)
        )
        source_frame = ttk.LabelFrame(details_frame, text="Fuente")
        source_frame.pack(fill="both", expand=True, pady=(0, 6))
        source_editor = tk.Text(source_frame, height=8, wrap="word", state="disabled")
        source_editor.pack(fill="both", expand=True, padx=6, pady=6)
        translation_frame = ttk.LabelFrame(details_frame, text="Traducción")
        translation_frame.pack(fill="both", expand=True)
        translation_editor = tk.Text(translation_frame, height=8, wrap="word")
        translation_editor.pack(fill="both", expand=True, padx=6, pady=6)

        action_frame = ttk.Frame(container)
        action_frame.pack(fill="x", pady=(8, 0))
        records = []
        selected = {"record": None}
        edit_buttons = []

        def set_editor_text(widget, value, editable):
            widget.configure(state="normal")
            widget.delete("1.0", "end")
            widget.insert("1.0", value)
            widget.configure(state="normal" if editable else "disabled")

        def show_record(_event=None):
            selection = result_list.curselection()
            if not selection:
                selected["record"] = None
                return
            record = records[selection[0]]
            selected["record"] = record
            reservation_text = ""
            if record["reserved"]:
                workers = ", ".join(
                    item.get("worker") or "desconocido"
                    for item in record["reservations"]
                )
                reservation_text = f" | RESERVADA por {workers}"
            flags = ", ".join(record["flags"]) or "sin flags"
            info_var.set(
                f"{record['id']} | estado={record['status']} | {flags}"
                f"{reservation_text}"
            )
            set_editor_text(source_editor, record["source"], False)
            set_editor_text(
                translation_editor,
                record["translation"],
                not record["reserved"],
            )
            state = "disabled" if record["reserved"] else "normal"
            for button in edit_buttons:
                button.configure(state=state)

        def refresh_entries(select_id=None):
            nonlocal records
            status_map = {
                "Pendientes": {"pending"},
                "Traducidas": {"translated"},
                "Revisadas": {"reviewed"},
                "Preservadas": {"preserved"},
            }
            try:
                records = search_entries(
                    project_path=config_path,
                    query=query_var.get(),
                    statuses=status_map.get(filter_var.get()),
                    limit=500,
                )
                if filter_var.get() == "Por revisar":
                    records = [
                        record for record in records
                        if "needs_review" in record["flags"]
                    ]
            except (CatalogEditError, OSError, ValueError, json.JSONDecodeError) as error:
                messagebox.showerror("No se pudo cargar el catálogo", str(error), parent=editor)
                return

            result_list.delete(0, "end")
            selected_index = None
            for index, record in enumerate(records):
                marker = "[RESERVADA] " if record["reserved"] else ""
                result_list.insert(
                    "end", f"{marker}{record['id']} | {record['status']}"
                )
                if record["id"] == select_id:
                    selected_index = index
            editor_status_var.set(f"Entradas mostradas: {len(records)}")
            if records:
                index = selected_index if selected_index is not None else 0
                result_list.selection_set(index)
                result_list.see(index)
                show_record()
            else:
                selected["record"] = None
                info_var.set("No hay entradas para este filtro.")
                set_editor_text(source_editor, "", False)
                set_editor_text(translation_editor, "", False)
                for button in edit_buttons:
                    button.configure(state="disabled")

        def apply_action(action, mark_reviewed=False):
            record = selected["record"]
            if record is None:
                return
            if action in {"requeue", "preserve"}:
                labels = {
                    "requeue": "devolver esta entrada a la cola",
                    "preserve": "preservar intencionalmente el texto fuente",
                }
                if not messagebox.askyesno(
                    "Confirmar acción",
                    f"¿Deseas {labels[action]}?",
                    parent=editor,
                ):
                    return
            translation = translation_editor.get("1.0", "end-1c")
            try:
                updated = commit_entry(
                    record["id"],
                    record["entry_revision"],
                    action,
                    project_path=config_path,
                    translation=translation if action == "save" else None,
                    mark_reviewed=mark_reviewed,
                )
            except (CatalogEditError, OSError, ValueError, json.JSONDecodeError) as error:
                messagebox.showerror("No se pudo guardar", str(error), parent=editor)
                refresh_entries(record["id"])
                return
            editor_status_var.set(f"Guardado: {updated['id']}")
            refresh_entries(updated["id"])

        search_button = ttk.Button(
            search_frame, text="Buscar", command=lambda: refresh_entries()
        )
        search_button.pack(side="left", padx=(8, 0))
        query_entry.bind("<Return>", lambda _event: refresh_entries())
        result_list.bind("<<ListboxSelect>>", show_record)

        for text, action, reviewed in (
            ("Guardar", "save", False),
            ("Guardar y revisar", "save", True),
            ("Marcar revisada", "review", False),
            ("Devolver a cola", "requeue", False),
            ("Preservar fuente", "preserve", False),
        ):
            button = ttk.Button(
                action_frame,
                text=text,
                command=lambda current_action=action, current_reviewed=reviewed: apply_action(
                    current_action, current_reviewed
                ),
            )
            button.pack(side="left", padx=(0, 6))
            edit_buttons.append(button)
        ttk.Button(
            action_frame, text="Actualizar", command=lambda: refresh_entries()
        ).pack(side="left", padx=(8, 0))
        ttk.Button(action_frame, text="Cerrar", command=editor.destroy).pack(side="right")
        ttk.Label(container, textvariable=editor_status_var).pack(
            anchor="w", pady=(6, 0)
        )
        apply_theme()
        refresh_entries()
        query_entry.focus_set()

    def open_translation_view():
        """Open the independent A/B translation and debug window.

        The window shows the source text (language A) and its translation
        (language B) side by side with contextual headers.  It reuses the
        existing catalog loading and editing flow (search_entries and
        commit_entry) and never modifies data automatically.  If the window
        is already open it is raised and focused instead of duplicated.
        """
        nonlocal translation_view_window
        if (
            translation_view_window is not None
            and translation_view_window.winfo_exists()
        ):
            translation_view_window.deiconify()
            translation_view_window.lift()
            translation_view_window.focus_set()
            return

        config_path = Path(config_var.get()).expanduser()
        if not config_path.exists():
            messagebox.showerror(
                "Proyecto no encontrado",
                "Prepara el proyecto o indica una configuración existente.",
            )
            return

        window = tk.Toplevel(root)
        window.title("Gandalf - Traducción A/B")
        window.geometry("1060x640")
        window.minsize(840, 520)
        translation_view_window = window

        container = ttk.Frame(window, padding=12)
        container.pack(fill="both", expand=True)

        info_var = tk.StringVar(value="Selecciona una entrada.")
        ttk.Label(container, textvariable=info_var, wraplength=980).pack(
            anchor="w", fill="x", pady=(0, 8)
        )

        search_frame = ttk.Frame(container)
        search_frame.pack(fill="x", pady=(0, 8))
        query_var = tk.StringVar()
        filter_var = tk.StringVar(value="Todas")
        window_status_var = tk.StringVar(value="Cargando entradas...")
        ttk.Label(search_frame, text="Buscar").pack(side="left")
        query_entry = ttk.Entry(search_frame, textvariable=query_var)
        query_entry.pack(side="left", fill="x", expand=True, padx=(6, 8))
        ttk.Combobox(
            search_frame,
            textvariable=filter_var,
            values=(
                "Todas",
                "Pendientes",
                "Traducidas",
                "Por revisar",
                "Revisadas",
                "Preservadas",
            ),
            state="readonly",
            width=14,
        ).pack(side="left")

        content = ttk.Panedwindow(container, orient="horizontal")
        content.pack(fill="both", expand=True)
        results_frame = ttk.LabelFrame(content, text="Entradas")
        details_frame = ttk.Frame(content)
        content.add(results_frame, weight=2)
        content.add(details_frame, weight=3)

        result_list = tk.Listbox(results_frame, exportselection=False)
        result_scroll = ttk.Scrollbar(
            results_frame, orient="vertical", command=result_list.yview
        )
        result_list.configure(yscrollcommand=result_scroll.set)
        result_list.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=6)
        result_scroll.pack(side="right", fill="y", padx=(0, 6), pady=6)

        source_title, target_title = translation_pane_labels(
            source_language_var.get(), target_language_var.get()
        )
        panes = ttk.Frame(details_frame)
        panes.pack(fill="both", expand=True)
        source_frame = ttk.LabelFrame(panes, text=source_title)
        source_frame.pack(side="left", fill="both", expand=True, padx=(0, 4))
        target_frame = ttk.LabelFrame(panes, text=target_title)
        target_frame.pack(side="left", fill="both", expand=True, padx=(4, 0))
        source_editor = tk.Text(source_frame, height=10, wrap="word", state="disabled")
        source_editor.pack(fill="both", expand=True, padx=6, pady=6)
        translation_editor = tk.Text(target_frame, height=10, wrap="word")
        translation_editor.pack(fill="both", expand=True, padx=6, pady=6)
        translation_view_widgets.extend((source_editor, translation_editor))

        action_frame = ttk.Frame(container)
        action_frame.pack(fill="x", pady=(8, 0))
        records = []
        selected = {"record": None}
        edit_buttons = []

        def set_editor_text(widget, value, editable):
            widget.configure(state="normal")
            widget.delete("1.0", "end")
            widget.insert("1.0", value)
            widget.configure(state="normal" if editable else "disabled")

        def show_record(_event=None):
            selection = result_list.curselection()
            if not selection:
                selected["record"] = None
                return
            record = records[selection[0]]
            selected["record"] = record
            info_var.set(format_entry_header(record))
            set_editor_text(source_editor, record["source"], False)
            set_editor_text(
                translation_editor,
                record["translation"],
                not record["reserved"],
            )
            state = "disabled" if record["reserved"] else "normal"
            for button in edit_buttons:
                button.configure(state=state)

        def refresh_entries(select_id=None):
            nonlocal records
            status_map = {
                "Pendientes": {"pending"},
                "Traducidas": {"translated"},
                "Revisadas": {"reviewed"},
                "Preservadas": {"preserved"},
            }
            try:
                records = search_entries(
                    project_path=config_path,
                    query=query_var.get(),
                    statuses=status_map.get(filter_var.get()),
                    limit=500,
                )
                if filter_var.get() == "Por revisar":
                    records = [
                        record for record in records
                        if "needs_review" in record["flags"]
                    ]
            except (CatalogEditError, OSError, ValueError, json.JSONDecodeError) as error:
                messagebox.showerror(
                    "No se pudo cargar el catálogo", str(error), parent=window
                )
                return

            result_list.delete(0, "end")
            selected_index = None
            for index, record in enumerate(records):
                marker = "[RESERVADA] " if record["reserved"] else ""
                result_list.insert(
                    "end", f"{marker}{record['id']} | {record['status']}"
                )
                if record["id"] == select_id:
                    selected_index = index
            window_status_var.set(f"Entradas mostradas: {len(records)}")
            if records:
                index = selected_index if selected_index is not None else 0
                result_list.selection_set(index)
                result_list.see(index)
                show_record()
            else:
                selected["record"] = None
                info_var.set("No hay entradas para este filtro.")
                set_editor_text(source_editor, "", False)
                set_editor_text(translation_editor, "", False)
                for button in edit_buttons:
                    button.configure(state="disabled")

        def select_relative(offset):
            if not records:
                return
            selection = result_list.curselection()
            index = selection[0] if selection else 0
            index = max(0, min(len(records) - 1, index + offset))
            result_list.selection_clear(0, "end")
            result_list.selection_set(index)
            result_list.see(index)
            show_record()

        def save_translation(mark_reviewed=False):
            record = selected["record"]
            if record is None:
                return
            translation = translation_editor.get("1.0", "end-1c")
            try:
                updated = commit_entry(
                    record["id"],
                    record["entry_revision"],
                    "save",
                    project_path=config_path,
                    translation=translation,
                    mark_reviewed=mark_reviewed,
                )
            except (CatalogEditError, OSError, ValueError, json.JSONDecodeError) as error:
                messagebox.showerror("No se pudo guardar", str(error), parent=window)
                refresh_entries(record["id"])
                return
            window_status_var.set(f"Guardado: {updated['id']}")
            refresh_entries(updated["id"])

        def close_translation_view():
            nonlocal translation_view_window
            translation_view_window = None
            translation_view_widgets.clear()
            window.destroy()

        search_button = ttk.Button(
            search_frame, text="Buscar", command=lambda: refresh_entries()
        )
        search_button.pack(side="left", padx=(8, 0))
        query_entry.bind("<Return>", lambda _event: refresh_entries())
        result_list.bind("<<ListboxSelect>>", show_record)

        for text, command in (
            ("Guardar", lambda: save_translation(False)),
            ("Guardar y revisar", lambda: save_translation(True)),
            ("Anterior", lambda: select_relative(-1)),
            ("Siguiente", lambda: select_relative(1)),
        ):
            button = ttk.Button(action_frame, text=text, command=command)
            button.pack(side="left", padx=(0, 6))
            edit_buttons.append(button)
        ttk.Button(
            action_frame, text="Actualizar", command=lambda: refresh_entries()
        ).pack(side="left", padx=(8, 0))
        ttk.Button(action_frame, text="Cerrar", command=close_translation_view).pack(
            side="right"
        )
        ttk.Label(container, textvariable=window_status_var).pack(
            anchor="w", pady=(6, 0)
        )

        window.protocol("WM_DELETE_WINDOW", close_translation_view)
        apply_theme()
        refresh_entries()
        query_entry.focus_set()

    def selected_farm_config():
        profile_path = resolve_workspace_path(farm_config_var.get())
        profile = load_farm_config_with_runtime_fallback(profile_path)
        project_path = resolve_workspace_path(config_var.get())
        if profile["project"] != project_path:
            raise ValueError(
                "El perfil de granja apunta a otro proyecto: "
                f"{profile['project']}"
            )
        return profile["config_path"], profile

    def use_farm_project():
        profile_path = resolve_workspace_path(farm_config_var.get())
        try:
            profile = load_farm_config(profile_path)
            project = load_project(profile["project"])
        except (OSError, ValueError, json.JSONDecodeError) as error:
            messagebox.showerror("Perfil de granja inválido", str(error))
            return
        project_path = profile["project"]
        try:
            project_text = str(project_path.relative_to(ROOT))
        except ValueError:
            project_text = str(project_path)
        config_var.set(project_text)
        catalog_var.set(project["catalog"])
        persist_settings()
        refresh_farm_status(schedule=False)

    def set_farm_buttons(
        active,
        mode,
        enabled=True,
        control_supported=True,
        project_changed=False,
        profile_available=True,
    ):
        states = farm_button_states(
            active,
            mode,
            enabled=enabled,
            control_supported=control_supported,
            project_changed=project_changed,
            profile_available=profile_available,
            action_running=farm_action_running,
        )
        for button, state in zip(
            (
                farm_start_button,
                farm_drain_button,
                farm_resume_button,
                farm_stop_button,
            ),
            states,
        ):
            button.configure(state=state)

    def schedule_farm_status_refresh():
        nonlocal farm_status_after_id
        if farm_status_after_id is None and root.winfo_exists():
            farm_status_after_id = root.after(5000, scheduled_farm_status_refresh)

    def scheduled_farm_status_refresh():
        nonlocal farm_status_after_id
        farm_status_after_id = None
        refresh_farm_status()

    def refresh_farm_status(schedule=True):
        nonlocal farm_status_refresh_running
        if farm_status_refresh_running:
            if schedule:
                schedule_farm_status_refresh()
            return
        try:
            _profile_path, profile = selected_farm_config()
        except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
            farm_status_var.set(f"Granja no disponible: {error}")
            set_farm_buttons(False, "stopped", enabled=False)
            if schedule:
                schedule_farm_status_refresh()
            return

        farm_status_refresh_running = True

        def finish_refresh(result, error):
            nonlocal farm_status_refresh_running
            farm_status_refresh_running = False
            if error is not None:
                farm_status_var.set(f"Granja no disponible: {error}")
                set_farm_buttons(False, "stopped", enabled=False)
                if schedule:
                    schedule_farm_status_refresh()
                return
            supervisor = result["supervisor"]
            queue = result["queue"]
            active_children = sum(
                1 for child in result["children"] if child.get("active")
            )
            mode_label = {
                "running": "activa",
                "draining": "drenando",
                "orphaned": "huérfana",
                "stopped": "detenida",
            }.get(supervisor["mode"], supervisor["mode"])
            prefix = (
                "Proyecto modificado: detén la granja"
                if supervisor["project_changed"]
                else (
                    "Perfil inválido: usando estado runtime"
                    if not supervisor["profile_available"]
                    else f"Granja {mode_label}"
                )
            )
            farm_status_var.set(
                f"{prefix} | coordinadores {active_children} | "
                f"incompletas {queue['eligible']} | reservadas {queue['reserved']} | "
                f"avance {queue['progress_percent']:.2f}%"
            )
            set_farm_buttons(
                supervisor["active"],
                supervisor["mode"],
                enabled=True,
                control_supported=supervisor["control_supported"],
                project_changed=supervisor["project_changed"],
                profile_available=supervisor["profile_available"],
            )
            if schedule:
                schedule_farm_status_refresh()

        def finish_status(result, error):
            try:
                root.after(0, finish_refresh, result, error)
            except RuntimeError:
                pass

        start_gandalf_worker(
            lambda: farm_status(profile),
            finish_status,
            "gandalf-farm-status",
        )

    def run_farm_action(action):
        nonlocal farm_action_running
        try:
            profile_path, _profile = selected_farm_config()
        except (OSError, ValueError, json.JSONDecodeError) as error:
            messagebox.showerror("Perfil de granja inválido", str(error))
            return
        if action == "stop" and not messagebox.askyesno(
            "Detener granja",
            "¿Deseas detener inmediatamente los coordinadores y liberar sus leases?",
        ):
            return

        command = gandalf_farm_command(action, profile_path)
        farm_action_running = True
        set_farm_buttons(False, "stopped", enabled=False)
        farm_status_var.set(f"Ejecutando acción de granja: {action}...")
        write_output(f"$ {' '.join(command)}\n")

        def worker():
            try:
                result = subprocess.run(
                    command,
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                )
                output = result.stdout + result.stderr
                root.after(0, finish_action, result.returncode, output)
            except OSError as error:
                root.after(0, finish_action, 1, f"Error: {error}\n")

        def finish_action(return_code, output):
            nonlocal farm_action_running
            farm_action_running = False
            write_output(output)
            if return_code:
                messagebox.showerror(
                    "Acción de granja fallida",
                    output.strip() or f"Código de salida {return_code}",
                )
            refresh_farm_status(schedule=False)

        threading.Thread(
            target=worker,
            name=f"gandalf-farm-{action}",
            daemon=True,
        ).start()

    def open_farm_logs():
        try:
            _profile_path, profile = selected_farm_config()
        except (OSError, ValueError, json.JSONDecodeError) as error:
            messagebox.showerror("Perfil de granja inválido", str(error))
            return
        window = tk.Toplevel(root)
        window.title("Gandalf - Logs de la granja")
        window.geometry("980x620")
        view = tk.Text(window, wrap="none", state="disabled")
        view.pack(fill="both", expand=True, padx=8, pady=(8, 4))
        logs_refresh_running = False

        def refresh_logs():
            nonlocal logs_refresh_running
            if logs_refresh_running:
                return
            logs_refresh_running = True
            refresh_logs_button.configure(state="disabled")

            def finish_logs(text):
                nonlocal logs_refresh_running
                logs_refresh_running = False
                if not window.winfo_exists():
                    return
                refresh_logs_button.configure(state="normal")
                view.configure(state="normal")
                view.delete("1.0", "end")
                view.insert("1.0", text)
                view.configure(state="disabled")

            def logs_worker():
                sections = []
                try:
                    log_names = ["supervisor.log"] + [
                        f"{coordinator['prefix']}.log"
                        for coordinator in profile["coordinators"]
                    ]
                    for name in log_names:
                        path = profile["log_directory"] / name
                        if not path.is_file():
                            continue
                        sections.append(
                            f"===== {path.name} =====\n" + read_log_tail(path)
                        )
                    text = "\n\n".join(sections) or "Todavía no hay logs."
                except OSError as error:
                    text = f"Error al leer logs: {error}"
                try:
                    root.after(0, finish_logs, text)
                except RuntimeError:
                    pass

            threading.Thread(
                target=logs_worker,
                name="gandalf-farm-logs",
                daemon=True,
            ).start()

        controls = ttk.Frame(window)
        controls.pack(fill="x", padx=8, pady=(0, 8))
        refresh_logs_button = ttk.Button(
            controls, text="Actualizar", command=refresh_logs
        )
        refresh_logs_button.pack(side="left")
        ttk.Button(controls, text="Cerrar", command=window.destroy).pack(side="right")
        refresh_logs()

    def pause_run():
        nonlocal process_paused
        if process_handle is None:
            return
        if platform.system() == "Windows":
            write_output("Pausa no disponible en Windows; usa el límite de tiempo.\n")
            return
        import signal
        try:
            if process_paused:
                process_handle.send_signal(signal.SIGCONT)
                process_paused = False
                pause_button.configure(text="Pausar")
                status_var.set("Ejecución reanudada.")
            else:
                process_handle.send_signal(signal.SIGSTOP)
                process_paused = True
                pause_button.configure(text="Reanudar")
                status_var.set("Ejecución pausada.")
        except OSError as error:
            write_output(f"Error al cambiar la pausa: {error}\n")

    def save_and_exit():
        nonlocal close_when_done
        if process_handle is None:
            root.destroy()
            return
        if process_paused:
            pause_run()
        close_when_done = True
        status_var.set("Guardando checkpoints y cerrando...")
        write_progress("Salida solicitada: se conservan las entradas ya completadas.")
        process_handle.terminate()

    def save_current():
        persist_settings()
        if process_handle is not None:
            status_var.set("Hay un proceso de construcción en curso.")
            return
        messagebox.showinfo("Guardar", "La configuración local está guardada.")

    def request_close():
        if process_handle is not None:
            messagebox.showinfo(
                "Lote en ejecución",
                "Gandalf esperará a que termine el proceso antes de cerrar.",
            )
            return
        root.destroy()

    buttons = ttk.Frame(frame)
    buttons.pack(fill="x", pady=(0, 8), before=form)
    create_button = ttk.Button(buttons, text="Preparar proyecto", command=create_project)
    create_button.pack(side="left")
    run_button = ttk.Button(buttons, text="Ejecutar", command=run_translation)
    run_button.pack(side="left", padx=(8, 0))
    build_button = ttk.Button(buttons, text="Construir prueba", command=build_test_package)
    build_button.pack(side="left", padx=(8, 0))
    correct_button = ttk.Button(
        buttons, text="Corregir entradas", command=open_catalog_editor
    )
    correct_button.pack(side="left", padx=(8, 0))
    translation_button = ttk.Button(
        buttons, text="Vista A/B", command=open_translation_view
    )
    translation_button.pack(side="left", padx=(8, 0))
    pause_button = ttk.Button(buttons, text="Pausar", command=pause_run, state="disabled")
    pause_button.pack(side="left", padx=(8, 0))
    ttk.Button(buttons, text="Abrir Debug", command=open_debug_window).pack(side="left", padx=(8, 0))
    exit_buttons = ttk.Frame(buttons)
    exit_buttons.pack(side="right")
    save_button = ttk.Button(exit_buttons, text="Guardar", command=save_current)
    save_button.pack(side="left")
    exit_button = ttk.Button(exit_buttons, text="Salir", command=request_close)
    exit_button.pack(side="left", padx=(8, 0))
    ttk.Label(frame, textvariable=status_var).pack(anchor="w", pady=(0, 8), before=form)
    add_tooltip(create_button, "Extrae el archivo .big y crea el catálogo y la configuración del proyecto.")
    add_tooltip(run_button, "Exporta un lote pequeño para un agente externo o abre el editor manual.")
    add_tooltip(build_button, "Construye y empaqueta un .big parcial usando el texto original como fallback.")
    add_tooltip(
        correct_button,
        "Busca y corrige entradas no reservadas sin detener workers activos.",
    )
    add_tooltip(
        translation_button,
        "Abre una ventana independiente con origen (A) y traducción (B) lado a lado.",
    )
    add_tooltip(pause_button, "Pausa o reanuda el proceso de construcción.")
    add_tooltip(save_button, "Guarda la configuración local de Gandalf.")
    add_tooltip(exit_button, "Cierra Gandalf cuando no haya un proceso activo.")

    farm_frame = ttk.LabelFrame(frame, text="Granja OpenCode")
    farm_frame.pack(fill="x", pady=(6, 8), before=progress_frame)
    farm_controls = ttk.Frame(farm_frame)
    farm_controls.pack(fill="x", padx=8, pady=(8, 4))
    farm_start_button = ttk.Button(
        farm_controls, text="Iniciar", command=lambda: run_farm_action("start")
    )
    farm_start_button.pack(side="left")
    farm_drain_button = ttk.Button(
        farm_controls, text="Drenar", command=lambda: run_farm_action("drain")
    )
    farm_drain_button.pack(side="left", padx=(6, 0))
    farm_resume_button = ttk.Button(
        farm_controls, text="Reanudar", command=lambda: run_farm_action("resume")
    )
    farm_resume_button.pack(side="left", padx=(6, 0))
    farm_stop_button = ttk.Button(
        farm_controls, text="Detener ahora", command=lambda: run_farm_action("stop")
    )
    farm_stop_button.pack(side="left", padx=(6, 0))
    ttk.Button(farm_controls, text="Abrir logs", command=open_farm_logs).pack(
        side="right"
    )
    ttk.Button(
        farm_controls, text="Usar proyecto del perfil", command=use_farm_project
    ).pack(side="right", padx=(0, 6))
    ttk.Label(farm_frame, textvariable=farm_status_var).pack(
        anchor="w", padx=8, pady=(0, 8)
    )
    set_farm_buttons(False, "stopped", enabled=False)
    root.protocol("WM_DELETE_WINDOW", request_close)
    persist_settings()
    root.after(250, refresh_farm_status)

    root.mainloop()


# ---------------------------------------------------------------------------
# Bulk translate: constants, registry, validation, plan, and execution
# ---------------------------------------------------------------------------

WORKER_MIN = 4
WORKER_MAX = 8
BATCH_SIZE_MIN = 1
BATCH_SIZE_MAX = 100

ALLOWED_MODELS_PATH = ROOT / "config" / "allowed_models.json"


def load_allowed_models():
    """Load the allowed_models.json registry."""
    with ALLOWED_MODELS_PATH.open(encoding="utf-8") as registry_file:
        return json.load(registry_file)


# Canonical tier ordering for deterministic iteration.
_TIER_ORDER = ("free", "economic", "premium")


def list_models_by_tier():
    """Return a dict mapping each tier to its sorted list of model IDs.

    Tiers are emitted in canonical order (free, economic, premium).  Model
    IDs within each tier are sorted lexicographically for deterministic
    output regardless of insertion order in the JSON file.
    """
    registry = load_allowed_models()
    grouped = {tier: [] for tier in _TIER_ORDER}
    for model_id, meta in registry["models"].items():
        tier = meta.get("tier", "unknown")
        if tier not in grouped:
            grouped[tier] = []
        grouped[tier].append(model_id)
    for tier in grouped:
        grouped[tier].sort()
    return grouped


def get_tier_models(tier):
    """Return the sorted list of model IDs for *tier*.

    Raises ``ValueError`` when *tier* is not one of the canonical tier
    names (``free``, ``economic``, ``premium``).
    """
    if tier not in _TIER_ORDER:
        raise ValueError(
            f"tier no válido: {tier}; opciones válidas: {', '.join(_TIER_ORDER)}"
        )
    grouped = list_models_by_tier()
    return grouped[tier]


def validate_model(model, *, confirmed=False):
    """Validate that *model* is in the allowed registry.

    Returns ``(model, tier)`` on success.  Raises ``ValueError`` when the
    model is unknown or is a premium model that requires explicit
    confirmation and *confirmed* is ``False``.

    Parameters
    ----------
    model : str
        Model identifier to validate.
    confirmed : bool, optional
        When ``True``, premium models that require confirmation are
        accepted.  When ``False`` (the default), they are rejected.
        Free and economic models are always accepted without confirmation.
    """
    if not isinstance(model, str) or not model:
        raise ValueError("modelo no permitido")
    registry = load_allowed_models()
    entry = registry["models"].get(model)
    if entry is None:
        raise ValueError(f"modelo no permitido: {model}")
    tier = entry.get("tier", "unknown")
    if tier == "premium" and entry.get("require_confirmation") and not confirmed:
        raise ValueError(
            f"el modelo {model} requiere confirmación explícita"
        )
    return model, tier


_TIER_LABELS = {
    "free": "Free (sin costo)",
    "economic": "Económico (bajo costo)",
    "premium": "Premium (alto costo, requiere confirmación)",
}

_TIER_ORDER_LABELS = {
    "free": "1",
    "economic": "2",
    "premium": "3",
}


def tier_label(tier):
    """Return a human-readable label for *tier*."""
    return _TIER_LABELS.get(tier, tier)


def tier_menu_key(tier):
    """Return the menu shortcut key for *tier*."""
    return _TIER_ORDER_LABELS.get(tier, "?")


def is_premium_tier(tier):
    """Return True when *tier* requires explicit user confirmation."""
    return tier == "premium"


def get_models_for_tier(tier):
    """Return the sorted list of model IDs for *tier*.

    Raises ``ValueError`` when *tier* is not one of the canonical tier
    names.
    """
    return get_tier_models(tier)


def select_model(tier, model_id, *, confirmed=False):
    """Validate and return ``(model_id, tier)`` for a UI selection.

    Parameters
    ----------
    tier : str
        Tier chosen by the user (``free``, ``economic``, or ``premium``).
    model_id : str
        Model identifier chosen by the user from the tier's list.
    confirmed : bool, optional
        Must be ``True`` for premium models that require confirmation.

    Returns
    -------
    tuple[str, str]
        ``(model_id, tier)`` on success.

    Raises
    ------
    ValueError
        When *tier* is invalid, *model_id* is not in the tier's list,
        or premium confirmation is missing.
    """
    if tier not in _TIER_ORDER:
        raise ValueError(
            f"tier no válido: {tier}; opciones válidas: {', '.join(_TIER_ORDER)}"
        )
    models = get_tier_models(tier)
    if model_id not in models:
        raise ValueError(
            f"el modelo {model_id} no pertenece al tier {tier}"
        )
    return validate_model(model_id, confirmed=confirmed)


def format_model_status(tier, model_id):
    """Return a short display string describing the current selection."""
    label = tier_label(tier)
    if model_id:
        return f"{label} — {model_id}"
    return f"{label} — (sin modelo seleccionado)"


def validate_workers(count):
    """Validate worker count is within the allowed range."""
    if not isinstance(count, int) or not WORKER_MIN <= count <= WORKER_MAX:
        raise ValueError(
            f"workers debe estar entre {WORKER_MIN} y {WORKER_MAX}"
        )
    return count


def validate_batch_size(count):
    """Validate per-worker batch size is within the allowed range."""
    if not isinstance(count, int) or not BATCH_SIZE_MIN <= count <= BATCH_SIZE_MAX:
        raise ValueError(
            f"per-worker-count debe estar entre {BATCH_SIZE_MIN} y {BATCH_SIZE_MAX}"
        )
    return count


def validate_total_entries(count):
    """Validate total requested entries is within the allowed range (20-100)."""
    if not isinstance(count, int) or not BATCH_SIZE_MIN <= count <= BATCH_SIZE_MAX:
        raise ValueError(
            f"total-entries debe estar entre {BATCH_SIZE_MIN} y {BATCH_SIZE_MAX}"
        )
    return count


def resolve_quantity(*, workers, per_worker_count=None, total_entries=None,
                     full_catalog=False, catalog_path=None):
    """Resolve the quantity configuration for a translation plan.

    Exactly one of *per_worker_count*, *total_entries*, or *full_catalog*
    must be active.

    Returns a dict with keys: ``total_entries``, ``per_worker_count``,
    ``requested_total``, ``full_catalog``.
    """
    modes = sum([
        per_worker_count is not None,
        total_entries is not None,
        full_catalog,
    ])
    if modes != 1:
        raise ValueError(
            "indique exactamente uno de: per-worker-count, total-entries, o full-catalog"
        )

    if per_worker_count is not None:
        validate_batch_size(per_worker_count)
        return {
            "total_entries": workers * per_worker_count,
            "per_worker_count": per_worker_count,
            "requested_total": None,
            "full_catalog": False,
        }

    if total_entries is not None:
        validate_total_entries(total_entries)
        per_worker = (total_entries + workers - 1) // workers
        return {
            "total_entries": total_entries,
            "per_worker_count": per_worker,
            "requested_total": total_entries,
            "full_catalog": False,
        }

    # full_catalog mode
    if catalog_path is None:
        raise ValueError("full-catalog requiere la ruta del catálogo")
    try:
        with Path(catalog_path).open(encoding="utf-8") as catalog_file:
            data = json.load(catalog_file)
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(
            f"no se pudo leer el catálogo para full-catalog: {error}"
        )
    entries = data.get("entries", [])
    pending = sum(1 for entry in entries if entry.get("status") == "pending")
    if pending == 0:
        raise ValueError(
            "el catálogo no contiene entradas pendientes para full-catalog"
        )
    per_worker = (pending + workers - 1) // workers
    return {
        "total_entries": pending,
        "per_worker_count": per_worker,
        "requested_total": None,
        "full_catalog": True,
    }


def derive_bulk_profile(real_profile, temp_dir, run_id, model, workers, count):
    """Create an isolated farm profile for a bulk translation run.

    The derived profile uses exactly one coordinator with *run_id* as prefix
    and *model* as the model, overriding whatever the real profile contained.
    Returns the path to the written profile JSON.
    """
    derived = {
        "project": real_profile.get("project"),
        "workers": workers,
        "count": count,
        "max_restarts": real_profile.get("max_restarts", 0),
        "poll_seconds": real_profile.get("poll_seconds", 5),
        "coordinators": [{"prefix": run_id, "model": model}],
    }
    profile_path = Path(temp_dir) / f"derived-farm-{run_id}.json"
    with profile_path.open("w", encoding="utf-8", newline="\n") as profile_file:
        json.dump(derived, profile_file, ensure_ascii=False, indent=2)
        profile_file.write("\n")
    return profile_path


def create_temp_farm_profile(real_profile, temp_dir, prefix, model, workers, count):
    """Legacy wrapper around :func:`derive_bulk_profile`."""
    return derive_bulk_profile(real_profile, temp_dir, prefix, model, workers, count)


def build_translate_plan(project_file, farm_file, model, workers, count=None,
                         *, total_entries=None, full_catalog=False):
    """Build an explicit execution plan for bulk translation.

    The plan is mode-independent: it contains every field needed by any
    execution mode (dry-run, no-save, yes).  The plan derives a single
    coordinator with the requested *model* and ignores the original profile's
    coordinators.

    Supports three quantity modes:
    - Legacy: specify *count* (per-worker-count), total = workers * count
    - Total entries: specify *total_entries*, per_worker_count derived
    - Full catalog: specify *full_catalog=True*, reads pending count from catalog

    The plan exposes ``requested_total`` (what the user asked for, or ``None``
    for legacy/full-catalog) separately from ``total_entries`` (the actual
    resolved total) and ``per_worker_count`` (the per-worker distribution).
    """
    model, tier = validate_model(model, confirmed=True)
    workers = validate_workers(workers)

    project_path = Path(project_file).resolve()
    project = load_project(project_path)
    catalog_path = resolve_project_path(project, "catalog")

    quantity = resolve_quantity(
        workers=workers,
        per_worker_count=count,
        total_entries=total_entries,
        full_catalog=full_catalog,
        catalog_path=catalog_path,
    )

    farm_data = json.loads(Path(farm_file).read_text(encoding="utf-8"))

    return {
        "project_file": project_path,
        "project_name": project["name"],
        "catalog_path": catalog_path,
        "language": project["language"],
        "model": model,
        "tier": tier,
        "workers": workers,
        "per_worker_count": quantity["per_worker_count"],
        "total_entries": quantity["total_entries"],
        "requested_total": quantity["requested_total"],
        "full_catalog": quantity["full_catalog"],
        "coordinators": [{"prefix": "bulk-run", "model": model}],
        "farm_file": Path(farm_file).resolve(),
        "farm_data": farm_data,
    }


def validate_isolated_catalog(catalog_path):
    """Validate the structural integrity of an isolated catalog.

    Returns a list of human-readable error strings.  An empty list means the
    catalog is structurally valid.
    """
    errors = []
    try:
        with Path(catalog_path).open(encoding="utf-8") as catalog_file:
            data = json.load(catalog_file)
    except (OSError, json.JSONDecodeError) as error:
        errors.append(f"error al leer catálogo: {error}")
        return errors

    if "entries" not in data:
        errors.append("catálogo no contiene campo 'entries'")
    return errors


def cleanup_temp_farm_runtime(temp_dir, prefix):
    """Remove temporary farm runtime files under *temp_dir*.

    Only the ``.agent/`` directory is removed; other artifacts (catalog
    clones, logs, responses) are preserved.
    """
    agent_dir = Path(temp_dir) / ".agent"
    if agent_dir.exists():
        shutil.rmtree(agent_dir)


# ── Mode execution policies ─────────────────────────────────────────────


def execute_translate_dry_run(project_file, farm_file, model, workers,
                               count=None, *, total_entries=None,
                               full_catalog=False):
    """Dry-run: validate inputs, build plan, show effective plan.

    No files are created, no workers started, no models called.
    """
    plan = build_translate_plan(
        project_file, farm_file, model, workers, count,
        total_entries=total_entries, full_catalog=full_catalog,
    )

    print(f"[dry-run] Perfil bulk derivado")
    print(f"  Proyecto: {plan['project_name']}")
    print(f"  Idioma: {plan['language']}")
    print(f"  Modelo: {plan['model']} (tier: {plan['tier']})")
    print(f"  Workers: {plan['workers']}")
    if plan["requested_total"] is not None:
        print(f"  Entradas solicitadas: {plan['requested_total']}")
    if plan["full_catalog"]:
        print(f"  Modo: full-catalog (todas las pendientes)")
    print(f"  Entradas por worker: {plan['per_worker_count']}")
    print(f"  Capacidad total: {plan['total_entries']}")
    print(f"  Coordinadores derivados:")
    for coord in plan["coordinators"]:
        print(f"    - prefix={coord['prefix']} model={coord['model']}")
    print(f"  [dry-run] Sin efectos secundarios.")
    return 0


def execute_translate_no_save(project_file, farm_file, model, workers,
                               count=None, *, total_entries=None,
                               full_catalog=False):
    """No-save: isolated lifecycle with artifacts preserved.

    Creates a persistent isolated directory (never a TemporaryDirectory that
    deletes on exit), clones the catalog, runs the farm synchronously (not
    detached), validates the clone, then cleans up only runtime/lease files.
    The catalog clone, logs, and results remain on disk for review.
    """
    plan = build_translate_plan(
        project_file, farm_file, model, workers, count,
        total_entries=total_entries, full_catalog=full_catalog,
    )

    # Persistent isolated directory – NOT a TemporaryDirectory
    run_id = f"nosave-{uuid.uuid4().hex[:8]}"
    isolated_base = ROOT / ".agent" / f"bulk-{run_id}"
    isolated_base.mkdir(parents=True, exist_ok=True)

    try:
        # 1. Clone catalog
        isolated_catalog = isolated_base / "catalog.json"
        shutil.copy2(plan["catalog_path"], isolated_catalog)

        # 2. Create derived project pointing to the cloned catalog
        isolated_project = isolated_base / "project.json"
        project_data = json.loads(
            Path(project_file).read_text(encoding="utf-8")
        )
        project_data["catalog"] = str(isolated_catalog)
        with isolated_project.open("w", encoding="utf-8", newline="\n") as pf:
            json.dump(project_data, pf, ensure_ascii=False, indent=2)
            pf.write("\n")

        # 3. Derive farm profile pointing to isolated project
        derived_profile = derive_bulk_profile(
            plan["farm_data"], isolated_base, run_id,
            plan["model"], plan["workers"], plan["per_worker_count"],
        )
        derived_data = json.loads(
            derived_profile.read_text(encoding="utf-8")
        )
        derived_data["project"] = str(isolated_project)
        with derived_profile.open("w", encoding="utf-8", newline="\n") as df:
            json.dump(derived_data, df, ensure_ascii=False, indent=2)
            df.write("\n")

        # 4. Run farm synchronously (NOT detached) and wait for lifecycle
        command = [
            sys.executable,
            str(LOCALIZATION_TOOLS / "opencode_farm.py"),
            "start",
            "--config",
            str(derived_profile),
        ]
        result = subprocess.run(
            command, cwd=ROOT, capture_output=True, text=True,
        )
        if result.returncode != 0:
            return result.returncode

        # 5. Validate the isolated catalog
        errors = validate_isolated_catalog(isolated_catalog)
        if errors:
            for error in errors:
                print(f"Error de validación: {error}", file=sys.stderr)
            return 1

        # 6. Clean up only runtime/lease files; preserve catalog & logs
        cleanup_temp_farm_runtime(isolated_base, run_id)

        print(f"Resultados no-save en: {isolated_base}")
        return 0
    except Exception:
        # On failure clean up runtime files but keep any partial results
        cleanup_temp_farm_runtime(isolated_base, run_id)
        raise


def execute_translate_yes(project_file, farm_file, model, workers,
                           count=None, *, total_entries=None,
                           full_catalog=False):
    """Yes: use derived profile on real catalog, normal persistence.

    Runs the farm synchronously on the real catalog.  The derived profile
    overrides the model, workers, and coordinator while the catalog and
    project remain the originals.  Results persist through the normal farm
    flow.
    """
    plan = build_translate_plan(
        project_file, farm_file, model, workers, count,
        total_entries=total_entries, full_catalog=full_catalog,
    )

    run_id = f"yes-{uuid.uuid4().hex[:8]}"
    runtime_dir = ROOT / ".agent"
    runtime_dir.mkdir(parents=True, exist_ok=True)

    # Derive farm profile with exactly one coordinator and the requested model
    derived_profile = derive_bulk_profile(
        plan["farm_data"], runtime_dir, run_id,
        plan["model"], plan["workers"], plan["per_worker_count"],
    )

    # Run farm synchronously (NOT detached)
    command = [
        sys.executable,
        str(LOCALIZATION_TOOLS / "opencode_farm.py"),
        "start",
        "--config",
        str(derived_profile),
    ]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    return result.returncode


def run_bulk_translate(args):
    """Entry point for ``--translate`` mode.  Validates arguments, builds
    the execution plan, and dispatches to the selected mode policy.
    """
    mode_count = sum([args.dry_run, args.no_save, args.yes])
    if mode_count == 0:
        print("Error: indique un modo (--dry-run, --no-save, o --yes)", file=sys.stderr)
        return 1
    if mode_count > 1:
        print(
            "Error: solo puede indicar un modo de ejecución",
            file=sys.stderr,
        )
        return 1

    if not args.model:
        print("Error: modelo requerido", file=sys.stderr)
        return 1

    # Validate mutual exclusivity of quantity options
    quantity_options = sum([
        args.per_worker_count is not None,
        args.total_entries is not None,
        args.full_catalog,
    ])
    if quantity_options > 1:
        print(
            "Error: solo puede indicar uno de: --per-worker-count, "
            "--total-entries, o --full-catalog",
            file=sys.stderr,
        )
        return 1

    quantity_kwargs = {}
    if args.total_entries is not None:
        quantity_kwargs["total_entries"] = args.total_entries
    elif args.full_catalog:
        quantity_kwargs["full_catalog"] = True
    elif args.per_worker_count is not None:
        quantity_kwargs["count"] = args.per_worker_count

    try:
        if args.dry_run:
            return execute_translate_dry_run(
                args.project,
                args.farm_profile,
                args.model,
                args.workers,
                **quantity_kwargs,
            )
        if args.no_save:
            return execute_translate_no_save(
                args.project,
                args.farm_profile,
                args.model,
                args.workers,
                **quantity_kwargs,
            )
        if args.yes:
            return execute_translate_yes(
                args.project,
                args.farm_profile,
                args.model,
                args.workers,
                **quantity_kwargs,
            )
    except (
        OSError,
        RuntimeError,
        ValueError,
        json.JSONDecodeError,
        subprocess.CalledProcessError,
    ) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


def main():
    parser = argparse.ArgumentParser(description="Gandalf project initialization wizard.")
    parser.add_argument("input", nargs="?", help="Extracted source JSON for non-interactive mode")
    parser.add_argument("output", nargs="?", help="Work catalog output for non-interactive mode")
    parser.add_argument("--force", action="store_true", help="Allow replacing an existing catalog")
    parser.add_argument("--wizard", action="store_true", help="Explicitly start the interactive wizard")
    parser.add_argument("--gui", action="store_true", help="Open the graphical project setup")
    parser.add_argument("--cli", action="store_true", help="Force the terminal wizard instead of the GUI")
    parser.add_argument(
        "--allow-same-language",
        action="store_true",
        help="Allow source and target languages with the same base code",
    )
    parser.add_argument(
        "--advanced",
        "--avanced",
        dest="advanced",
        action="store_true",
        help="Allow custom language codes and advanced project options",
    )
    parser.add_argument("--source-language", help="Override detected source language")
    parser.add_argument("--target-language", help="Override target language")
    # Bulk translate mode
    parser.add_argument("--translate", action="store_true", help="Run bulk translation")
    parser.add_argument("--project", help="Project configuration JSON for --translate")
    parser.add_argument("--farm-profile", help="Farm profile JSON for --translate")
    parser.add_argument("--model", help="Model for translation (required for --translate)")
    parser.add_argument("--workers", type=int, help="Number of workers (4-8)")
    parser.add_argument("--per-worker-count", type=int, help="Entries per worker (1-100)")
    parser.add_argument("--total-entries", type=int, help="Total entries to translate (1-100)")
    parser.add_argument("--full-catalog", action="store_true", help="Translate all pending entries in the catalog")
    parser.add_argument("--dry-run", action="store_true", help="Show plan without side effects")
    parser.add_argument("--no-save", action="store_true", help="Isolated run, preserve artifacts")
    parser.add_argument("--yes", action="store_true", help="Execute on real catalog")
    args = parser.parse_args()
    try:
        if args.translate:
            return run_bulk_translate(args)
        if args.gui:
            launch_gui()
            return 0
        if not args.input and not args.wizard and not args.cli:
            try:
                launch_gui()
                return 0
            except RuntimeError as error:
                print(f"Aviso: {error}. Se inicia el wizard de terminal.", file=sys.stderr)
        if args.wizard or not args.input:
            wizard(
                args.force,
                args.allow_same_language,
                args.advanced,
                args.source_language,
                args.target_language,
            )
        else:
            print(f"Catalogo creado: {args.output}")
            print(f"Entradas: {non_interactive(args)}")
        return 0
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError, subprocess.CalledProcessError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
