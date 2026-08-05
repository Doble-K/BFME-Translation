#!/usr/bin/env python3

import argparse
import json
import platform
import subprocess
import sys
import tempfile
from pathlib import Path

from tools.localization.extract import extract_str


ROOT = Path(__file__).resolve().parent
AUTO_ID_PREFIXES = ("LETTER:", "NUMBER:")


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


def main():
    parser = argparse.ArgumentParser(description="Gandalf project initialization wizard.")
    parser.add_argument("input", nargs="?", help="Extracted source JSON for non-interactive mode")
    parser.add_argument("output", nargs="?", help="Work catalog output for non-interactive mode")
    parser.add_argument("--force", action="store_true", help="Allow replacing an existing catalog")
    parser.add_argument("--wizard", action="store_true", help="Explicitly start the interactive wizard")
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
    except (OSError, ValueError, json.JSONDecodeError, subprocess.CalledProcessError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
