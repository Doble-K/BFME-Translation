#!/usr/bin/env python3

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

from project import load_project, resolve_project_path


URL_PATTERN = re.compile(r"https?://\S+", re.IGNORECASE)
BRACKET_HOTKEY_PATTERN = re.compile(r"\[&([^\s])\]")
BARE_HOTKEY_PATTERN = re.compile(r"&([^\s])")


def hotkey_letter(text):
    searchable = URL_PATTERN.sub("", text or "")
    bracket = BRACKET_HOTKEY_PATTERN.search(searchable)
    if bracket:
        return bracket.group(1).upper()
    bare = BARE_HOTKEY_PATTERN.search(searchable)
    return bare.group(1).upper() if bare else None


def normalize_segment(text, letter):
    text = BRACKET_HOTKEY_PATTERN.sub("", text)
    end = len(text.rstrip())

    def remove_marker(match):
        if match.end() == end and (match.start() == 0 or text[match.start() - 1].isspace()):
            return ""
        return match.group(1)

    text = BARE_HOTKEY_PATTERN.sub(remove_marker, text)
    return f"{text.rstrip()} [&{letter}]"


def normalize_hotkey_text(text, letter):
    if not text or not letter:
        return text
    pieces = []
    cursor = 0
    for match in URL_PATTERN.finditer(text):
        pieces.append(normalize_segment(text[cursor:match.start()], letter))
        pieces.append(match.group(0))
        cursor = match.end()
    pieces.append(normalize_segment(text[cursor:], letter))
    return "".join(pieces)


def save_catalog(path, data):
    temporary_path = path.with_name(f".{path.name}.tmp")
    try:
        with temporary_path.open("w", encoding="utf-8", newline="\n") as catalog_file:
            json.dump(data, catalog_file, ensure_ascii=False, indent=2)
            catalog_file.write("\n")
        os.replace(temporary_path, path)
    except OSError:
        if temporary_path.exists():
            temporary_path.unlink()
        raise


def main():
    parser = argparse.ArgumentParser(
        description="Move SAGE hotkeys to the standard trailing '[&X]' form."
    )
    parser.add_argument("catalog", nargs="?", help="Path to the work catalog")
    parser.add_argument("--project", help="Project configuration JSON")
    parser.add_argument("--write", action="store_true", help="Write normalized translations")
    args = parser.parse_args()

    try:
        project = load_project(args.project) if args.project else None
        if not args.catalog and not project:
            parser.error("indique catalog o use --project")
        catalog_path = Path(args.catalog) if args.catalog else resolve_project_path(project, "catalog")
        data = json.loads(catalog_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError) as error:
        print(f"Error: no se pudo cargar el catálogo: {error}", file=sys.stderr)
        return 1

    changed = []
    today = datetime.now().strftime("%Y-%m-%d")
    for entry in data.get("entries", []):
        translation = entry.get("translation", "")
        if not translation:
            continue
        source_hotkeys = BARE_HOTKEY_PATTERN.findall(URL_PATTERN.sub("", entry.get("source", "")))
        translation_hotkeys = BARE_HOTKEY_PATTERN.findall(URL_PATTERN.sub("", translation))
        if len(source_hotkeys) > 1 or len(translation_hotkeys) > 1:
            print(f"AVISO: más de un hotkey; se omite {entry.get('id')}")
            continue
        letter = hotkey_letter(entry.get("source", "")) or hotkey_letter(translation)
        if not letter:
            continue
        normalized = normalize_hotkey_text(translation, letter)
        if normalized == translation:
            continue
        changed.append((entry, translation, normalized))
        if args.write:
            entry["translation"] = normalized
            entry.setdefault("history", []).append({
                "date": today,
                "action": "hotkey_normalized",
                "from": translation,
                "to": normalized,
                "by": "system",
            })

    for entry, old_value, new_value in changed:
        print(f"{entry.get('id')}: {old_value} -> {new_value}")
    print(f"Hotkeys que requieren normalización: {len(changed)}")
    if not args.write:
        print("Preview: no se modificó el catálogo.")
        return 0
    try:
        save_catalog(catalog_path, data)
    except OSError as error:
        print(f"Error: no se pudo guardar el catálogo: {error}", file=sys.stderr)
        return 1
    print(f"Catálogo actualizado: {catalog_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
