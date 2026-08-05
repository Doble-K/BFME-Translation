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
from pathlib import Path

from tools.localization.extract import extract_str


ROOT = Path(__file__).resolve().parent
AUTO_ID_PREFIXES = ("LETTER:", "NUMBER:")
GANDALF_CONFIG_PATH = ROOT / "config" / "gandalf.local.json"


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
        "1": ("es", "Español"),
        "2": ("en", "English"),
        "3": ("pr", "Português"),
        "4": ("fr", "Français"),
        "5": ("ge", "Deutsch"),
    }
    print(f"Idioma {label}:")
    for number, (code, name) in languages.items():
        print(f"  {number}. {code} - {name}")
    choice = ask("Selecciona una opcion", "1" if default == "es" else "2")
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
        (("spanish", "espanol", "español"), "es"),
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


def handoff_to_translation(output_path, config_path, settings, advanced):
    print("\nSiguiente paso:")
    print("  1. Iniciar batch manual")
    print("  2. Ejecutar bulk con Ollama (dry-run por defecto)")
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
        write = ask("¿Guardar resultados de Ollama? (s/N)", "n")
        command = [
            sys.executable,
            str(ROOT / "tools/localization/ai_translate.py"),
            "--project",
            str(config_path),
            "--provider",
            "ollama",
            "--mode",
            "translate",
            "--routing",
            "auto",
            "--count",
            str(count),
        ]
        max_seconds = ask("Tiempo máximo en segundos (0 sin límite)", "300")
        try:
            if float(max_seconds) < 0:
                raise ValueError
        except ValueError as error:
            raise ValueError("El tiempo máximo debe ser un número no negativo") from error
        command.extend(("--max-seconds", max_seconds))
        if write.lower() in {"s", "si", "sí", "y", "yes"}:
            command.append("--write")
        else:
            command.append("--dry-run")
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
        target_language = choose_language("de destino", "es")
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
    root.geometry("760x620")
    root.minsize(680, 520)

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
    languages = {"Español": "es", "English": "en", "Português": "pr", "Français": "fr", "Deutsch": "ge"}
    candidates = find_big_files()
    saved_config = load_gandalf_config()
    saved_last = saved_config.get("last", {}) if isinstance(saved_config.get("last", {}), dict) else {}
    saved_ai = saved_config.get("ai", saved_config) if isinstance(saved_config, dict) else {}

    project_var = tk.StringVar(value=saved_last.get("project", "BFME2 ROTWK 2.02"))
    source_var = tk.StringVar(value=saved_last.get("source", str(candidates[0] if candidates else ROOT / "sources/englishpatch202.big")))
    source_language_var = tk.StringVar(value=saved_last.get("source_language", "English"))
    target_language_var = tk.StringVar(value=saved_last.get("target_language", "Español"))
    encoding_var = tk.StringVar(value=saved_last.get("encoding", "cp1252"))
    catalog_var = tk.StringVar(value=saved_last.get("catalog", "catalogs/bfme2-rotwk-2.02_es_work.json"))
    config_var = tk.StringVar(value=saved_last.get("config", "config/bfme2-rotwk-2.02_es.json"))
    force_var = tk.BooleanVar(value=False)
    dark_mode_var = tk.BooleanVar(value=False)
    run_mode_var = tk.StringVar(value=saved_last.get("mode", "IA Ollama"))
    run_count_var = tk.StringVar(value=saved_last.get("count", "20"))
    run_max_seconds_var = tk.StringVar(value=saved_last.get("max_seconds", "300"))
    run_write_var = tk.BooleanVar(value=saved_last.get("write", False))
    provider_var = tk.StringVar(value=saved_ai.get("provider", "ollama"))
    ollama_url_var = tk.StringVar(value=saved_ai.get("ollama_url", "http://127.0.0.1:11434"))
    small_model_var = tk.StringVar(value=saved_ai.get("small_model", "llama3.2:3b"))
    large_model_var = tk.StringVar(value=saved_ai.get("large_model", "qwen2.5:7b"))
    timeout_var = tk.StringVar(value=str(saved_ai.get("timeout", 300)))
    status_var = tk.StringVar(value="Listo para preparar un proyecto.")
    process_handle = None
    worker_thread = None
    process_paused = False
    close_when_done = False

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
    ttk.Checkbutton(form, text="Reemplazar archivos existentes", variable=force_var).pack(anchor="w", pady=8)

    run_frame = ttk.LabelFrame(frame, text="Ejecutar traducción")
    run_frame.pack(fill="x", pady=(8, 0))
    run_controls = ttk.Frame(run_frame)
    run_controls.pack(fill="x", padx=8, pady=8)
    ttk.Label(run_controls, text="Modo").pack(side="left")
    ttk.Combobox(
        run_controls,
        textvariable=run_mode_var,
        values=("IA Ollama", "Manual (terminal)"),
        state="readonly",
        width=18,
    ).pack(side="left", padx=(6, 12))
    ttk.Label(run_controls, text="Entradas").pack(side="left")
    ttk.Entry(run_controls, textvariable=run_count_var, width=7).pack(side="left", padx=(6, 12))
    ttk.Label(run_controls, text="Máx. segundos").pack(side="left")
    ttk.Entry(run_controls, textvariable=run_max_seconds_var, width=7).pack(side="left", padx=(6, 12))
    ttk.Checkbutton(run_controls, text="Guardar IA", variable=run_write_var).pack(side="left")
    ai_config = ttk.Frame(run_frame)
    ai_config.pack(fill="x", padx=8, pady=(0, 8))
    ttk.Label(ai_config, text="Proveedor").pack(side="left")
    provider_widget = ttk.Entry(ai_config, textvariable=provider_var, width=10)
    provider_widget.pack(side="left", padx=(6, 12))
    ttk.Label(ai_config, text="URL").pack(side="left")
    url_widget = ttk.Entry(ai_config, textvariable=ollama_url_var, width=25)
    url_widget.pack(side="left", padx=(6, 12))
    ttk.Label(ai_config, text="Modelo corto").pack(side="left")
    small_model_widget = ttk.Entry(ai_config, textvariable=small_model_var, width=16)
    small_model_widget.pack(side="left", padx=(6, 12))
    ttk.Label(ai_config, text="Modelo largo").pack(side="left")
    large_model_widget = ttk.Entry(ai_config, textvariable=large_model_var, width=16)
    large_model_widget.pack(side="left", padx=(6, 12))
    input_widgets.extend((provider_widget, url_widget, small_model_widget, large_model_widget))

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
        for text_widget in (source_view, target_view, debug_view):
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
                "ai": {
                    "provider": provider_var.get().strip() or "ollama",
                    "ollama_url": ollama_url_var.get().strip() or "http://127.0.0.1:11434",
                    "small_model": small_model_var.get().strip() or "llama3.2:3b",
                    "large_model": large_model_var.get().strip() or "qwen2.5:7b",
                    "timeout": int(timeout_var.get() or 300),
                },
                "last": {
                    "project": project_var.get(),
                    "source": source_var.get(),
                    "source_language": source_language_var.get(),
                    "target_language": target_language_var.get(),
                    "encoding": encoding_var.get(),
                    "catalog": catalog_var.get(),
                    "config": config_var.get(),
                    "mode": run_mode_var.get(),
                    "count": run_count_var.get(),
                    "max_seconds": run_max_seconds_var.get(),
                    "write": run_write_var.get(),
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
        for widget in input_widgets:
            widget.configure(state="disabled")
        threading.Thread(target=worker, daemon=True).start()

    def finish(message, success):
        write_output(message)
        status_var.set("Proyecto listo." if success else "La operación terminó con errores.")
        create_button.configure(state="normal")
        run_button.configure(state="normal")
        build_button.configure(state="normal")
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
        nonlocal process_handle, worker_thread
        persist_settings()
        try:
            count = int(run_count_var.get())
            max_seconds = float(run_max_seconds_var.get())
            request_timeout = int(timeout_var.get())
            if count < 1 or max_seconds < 0 or request_timeout < 1:
                raise ValueError
        except ValueError as error:
            messagebox.showerror("Valores inválidos", "Entradas debe ser mayor que cero y el tiempo no negativo.")
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
            str(ROOT / "tools/localization/ai_translate.py"),
            "--project",
            str(config_path),
            "--provider",
            provider_var.get().strip() or "ollama",
            "--mode",
            "translate",
            "--routing",
            "auto",
            "--count",
            str(count),
            "--max-seconds",
            str(max_seconds),
            "--ollama-url",
            ollama_url_var.get().strip() or "http://127.0.0.1:11434",
            "--small-model",
            small_model_var.get().strip() or "llama3.2:3b",
            "--large-model",
            large_model_var.get().strip() or "qwen2.5:7b",
            "--timeout",
            str(request_timeout),
            "--write" if run_write_var.get() else "--dry-run",
        ]
        if run_write_var.get():
            command.append("--checkpoint")
        write_output(f"$ {' '.join(command)}\n")
        progress_bar.configure(maximum=count, value=0)
        completed_ids.clear()
        completed_records.clear()
        completed_selector.configure(values=())
        completed_var.set("")
        set_text(source_view, "")
        set_text(target_view, "Esperando resultado...")
        run_button.configure(state="disabled")
        create_button.configure(state="disabled")
        build_button.configure(state="disabled")
        pause_button.configure(state="normal")
        for widget in input_widgets:
            widget.configure(state="disabled")
        status_var.set("Ejecutando Ollama...")

        def worker():
            nonlocal process_handle
            try:
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
                root.after(0, run_finished, return_code)
            except OSError as error:
                log_line(f"Error: {error}")
                root.after(0, run_finished, 1)

        worker_thread = threading.Thread(target=worker, name="gandalf-ollama", daemon=False)
        worker_thread.start()

    def run_finished(return_code):
        nonlocal process_handle, worker_thread, process_paused, close_when_done
        process_handle = None
        worker_thread = None
        process_paused = False
        run_button.configure(state="normal")
        create_button.configure(state="normal")
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
        if not run_write_var.get():
            messagebox.showwarning(
                "Dry-run activo",
                "El lote no está configurado para guardar. Marca 'Guardar IA' antes de salir.",
            )
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
            if not run_write_var.get():
                messagebox.showwarning("Dry-run activo", "Este lote no está configurado para guardar.")
                return
            status_var.set("Guardado automático activo: cada entrada completada se conserva por checkpoint.")
            write_output("Guardar: los resultados completados ya están guardados por checkpoint.\n")
            return
        messagebox.showinfo("Guardar", "No hay un lote activo. Los cambios guardados ya están en el catálogo.")

    def request_close():
        if process_handle is not None:
            messagebox.showinfo(
                "Lote en ejecución",
                "Gandalf esperará a que termine Ollama antes de cerrar. Usa un límite de tiempo si tarda demasiado.",
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
    add_tooltip(run_button, "Ejecuta el lote seleccionado: IA Ollama o editor manual en terminal.")
    add_tooltip(build_button, "Construye y empaqueta un .big parcial usando el texto original como fallback.")
    add_tooltip(pause_button, "Pausa o reanuda el proceso de IA sin cerrar Gandalf.")
    add_tooltip(save_button, "Confirma el guardado por checkpoint de las entradas ya completadas.")
    add_tooltip(exit_button, "Cierra Gandalf; si hay IA activa, espera o conserva el lote según su estado.")
    root.protocol("WM_DELETE_WINDOW", request_close)
    persist_settings()

    root.mainloop()


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
    args = parser.parse_args()
    try:
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
