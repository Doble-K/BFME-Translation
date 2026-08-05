#!/usr/bin/env python3

import argparse
import json
import platform
import subprocess
import sys
import tempfile
from pathlib import Path

from extract import extract_str


ROOT = Path(__file__).resolve().parents[2]


def greet():
    print(r"""
                         /\
                        /  \
                   ____/____\____
                  /      ||      \
                 /   _   ||   _   \
                /___|_|__||__|_|___\
                |      MINAS       |
                |      TIRITH       |
                |  [] [] || [] []   |
                |______  ||  _______|
                       \||/
                  /\    ||    /\
                 /  \   ||   /  \
                / WHITE HORSE  \
                   /\        /\
                  /  \______/  \
""")
    print("Bienvenido, viajero. Las puertas de Minas Tirith estan abiertas.")
    print("Gandalf preparara tu proyecto de localizacion.\n")


def ask(prompt, default=None):
    suffix = f" [{default}]" if default else ""
    value = input(f"{prompt}{suffix}: ").strip()
    return value or default


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


def choose_big_file():
    candidates = find_big_files()
    if candidates:
        print("Archivos .big detectados:")
        for index, path in enumerate(candidates, 1):
            print(f"  {index}. {path.relative_to(ROOT)}")
        choice = ask("Selecciona un archivo o escribe una ruta", "1")
        if choice.isdigit() and 1 <= int(choice) <= len(candidates):
            return candidates[int(choice) - 1]
        return Path(choice)
    return Path(ask("Ruta del archivo .big de origen"))


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
    for entry in data["entries"]:
        result["entries"].append({
            "id": entry["id"],
            "source": entry["text"],
            "translation": "",
            "status": "pending",
            "line": entry["line"],
            "flags": [],
            "notes": "",
            "translation_meta": {
                "origin": None,
                "model": None,
                "date": None,
                "confidence": 0.0,
            },
            "review": {
                "ai": {"checked": False, "issues": [], "last_review": None},
                "human": {"checked": False, "user": None, "date": None},
            },
            "history": [],
        })
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as output_file:
        json.dump(result, output_file, ensure_ascii=False, indent=2)
        output_file.write("\n")
    return len(result["entries"])


def wizard():
    greet()
    project = choose_project()
    big_file = choose_big_file()
    source_language = ask("Idioma de origen", "en-US")
    target_language = ask("Idioma de destino", "es-419")
    slug = project["slug"]
    output_path = Path(ask(
        "Catalogo de trabajo de salida",
        f"catalogs/{slug}_{target_language}_work.json",
    ))
    temporary_directory, string_file, entries = extract_source(big_file)
    try:
        source_data = {"source": str(string_file), "entries": entries}
        settings = {
            "project": project,
            "source_language": source_language,
            "target_language": target_language,
            "source_archive": str(big_file),
        }
        count = create_catalog(source_data, output_path, settings)
    finally:
        temporary_directory.cleanup()
    print(f"Catalogo creado: {output_path}")
    print(f"Entradas: {count}")
    print(f"Proyecto: {project['name']}")
    print(f"Idioma: {source_language} -> {target_language}")


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
        "force": args.force,
    }
    return create_catalog(data, output_path, settings)


def main():
    parser = argparse.ArgumentParser(description="Gandalf project initialization wizard.")
    parser.add_argument("input", nargs="?", help="Extracted source JSON for non-interactive mode")
    parser.add_argument("output", nargs="?", help="Work catalog output for non-interactive mode")
    parser.add_argument("--force", action="store_true", help="Allow replacing an existing catalog")
    parser.add_argument("--wizard", action="store_true", help="Explicitly start the interactive wizard")
    args = parser.parse_args()
    try:
        if args.wizard or not args.input:
            wizard()
        else:
            print(f"Catalogo creado: {args.output}")
            print(f"Entradas: {non_interactive(args)}")
        return 0
    except (OSError, ValueError, json.JSONDecodeError, subprocess.CalledProcessError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
