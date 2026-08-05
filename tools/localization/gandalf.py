#!/usr/bin/env python3

import argparse
import json
import sys
from pathlib import Path


def ask(prompt, default=None):
    suffix = f" [{default}]" if default else ""
    value = input(f"{prompt}{suffix}: ").strip()
    return value or default


def choose_project():
    print("Tipo de proyecto:")
    print("  1. BFME2 ROTWK 2.02")
    print("  2. Age of the Ring")
    print("  3. Otro mod o juego SAGE")
    choice = ask("Selecciona una opción", "1")
    if choice == "1":
        return "bfme2-rotwk-2.02", "BFME2 ROTWK 2.02", None
    if choice == "2":
        return "age-of-the-ring", "Age of the Ring", None
    project_slug = ask("Nombre corto del proyecto", "custom-sage-project")
    description = ask("Descripción del proyecto", "Otro mod o juego SAGE")
    return (
        project_slug,
        project_slug,
        description,
    )


def wizard_settings():
    project_slug, project_name, description = choose_project()
    source_archive = ask("Archivo .big/.str de origen (opcional)", "")
    source_language = ask("Idioma de origen", "en-US")
    target_language = ask("Idioma de destino", "es-419")
    source_catalog = ask("Catálogo JSON de fuente extraído", "catalogs/english.json")
    output_catalog = ask(
        "Catálogo de trabajo de salida",
        f"catalogs/{project_slug}_{target_language}_work.json",
    )
    return {
        "project": {
            "slug": project_slug,
            "name": project_name,
            "description": description,
        },
        "source_archive": source_archive or None,
        "source_language": source_language,
        "target_language": target_language,
        "source_catalog": source_catalog,
        "output_catalog": output_catalog,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Create a work catalog from an extracted source catalog."
    )
    parser.add_argument("input", nargs="?", help="Extracted source JSON")
    parser.add_argument("output", nargs="?", help="New work catalog JSON")
    parser.add_argument(
        "--wizard",
        action="store_true",
        help="Ask project, source language, target language, and output settings",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow replacing an existing output catalog",
    )
    args = parser.parse_args()

    settings = wizard_settings() if args.wizard or not args.input else None
    if settings:
        source_file = settings["source_catalog"]
        output_path = Path(settings["output_catalog"])
    else:
        if not args.input or not args.output:
            parser.error("indique input y output, o use --wizard")
        source_file = args.input
        output_path = Path(args.output)

    if output_path.exists() and not args.force:
        print(
            f"Error: el catálogo de salida ya existe: {output_path}. "
            "Use --force solo si desea reemplazarlo.",
            file=sys.stderr,
        )
        return 1

    try:
        with open(source_file, encoding="utf-8") as source_handle:
            data = json.load(source_handle)
    except (OSError, json.JSONDecodeError) as error:
        print(f"Error: no se pudo leer el catálogo fuente: {error}", file=sys.stderr)
        return 1

    result = {
        "source": data["source"],
        "language": settings["target_language"] if settings else "Spanish",
        "entries": [],
    }
    if settings:
        result["project"] = settings["project"]
        result["source_archive"] = settings["source_archive"]
        result["source_language"] = settings["source_language"]
        result["target_language"] = settings["target_language"]

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
    with output_path.open("w", encoding="utf-8", newline="\n") as output_handle:
        json.dump(result, output_handle, ensure_ascii=False, indent=2)
        output_handle.write("\n")

    print(f"Created {output_path}")
    print(f"Entries: {len(result['entries'])}")
    if settings:
        print(f"Project: {settings['project']['name']}")
        print(f"Language: {settings['source_language']} -> {settings['target_language']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
