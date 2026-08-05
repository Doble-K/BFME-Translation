#!/usr/bin/env python3

import json
import sys
import argparse
from pathlib import Path

from normalize_escapes import normalize_data


def main():
    parser = argparse.ArgumentParser(description="Build an SAGE localization string file.")
    parser.add_argument("catalog", help="Path to the localization catalog")
    parser.add_argument("output", help="Path to the output .str file")
    parser.add_argument("--encoding", default="cp1252", help="Output encoding")
    parser.add_argument("--debug", action="store_true", help="Use debug marker translations")
    parser.add_argument(
        "--allow-source-fallback",
        action="store_true",
        help="Use source text when a translation is empty",
    )
    parser.add_argument(
        "--exclude-id",
        action="append",
        default=[],
        help="Exclude an exact ID from this build; may be repeated",
    )
    parser.add_argument(
        "--exclude-whitespace-ids",
        action="store_true",
        help="Debug-only filter for IDs containing no non-whitespace characters",
    )
    parser.add_argument(
        "--dedupe-ids",
        choices=("first", "last"),
        help="Debug-only duplicate policy for non-whitespace IDs",
    )
    args = parser.parse_args()

    catalog_file = Path(args.catalog)
    output_str_file = Path(args.output)
    encoding = args.encoding
    debug = args.debug

    with open(catalog_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    normalized_count = normalize_data(data)
    if normalized_count:
        print(f"Secuencias de escape normalizadas durante el build: {normalized_count}")

    if debug:
        for entry in data.get("entries", []):
            if entry.get("id") in {"GUI:SinglePlayer", "APT:SoloPlay"}:
                entry["translation"] = "DEBUGING"
                print(f"Modo debug: {entry['id']} = DEBUGING")

    entries = data.get("entries", [])
    deduped_ids = []
    if args.dedupe_ids:
        selected = {}
        source_entries = entries if args.dedupe_ids == "first" else reversed(entries)
        for entry in source_entries:
            entry_id = entry.get("id")
            if entry_id and entry_id.strip() and entry_id not in selected:
                selected[entry_id] = entry
            elif entry_id and entry_id.strip():
                deduped_ids.append(entry_id)
        entries = (
            [entry for entry in entries if selected.get(entry.get("id")) is entry]
            if args.dedupe_ids == "first"
            else list(reversed(list(selected.values())))
        )
    excluded_ids = set(args.exclude_id)
    excluded_count = 0
    compiled_count = 0
    fallback_count = 0

    missing_translations = [
        entry.get("id", f"<índice {index}>")
        for index, entry in enumerate(entries)
        if entry.get("id") and not entry.get("translation")
    ]
    if missing_translations and not args.allow_source_fallback:
        print(
            "Error: faltan traducciones; use --allow-source-fallback solo para builds parciales.",
            file=sys.stderr,
        )
        print(f"Entradas sin traducción: {len(missing_translations)}", file=sys.stderr)
        for entry_id in missing_translations[:20]:
            print(f"  - {entry_id}", file=sys.stderr)
        if len(missing_translations) > 20:
            print(f"  ... y {len(missing_translations) - 20} más", file=sys.stderr)
        sys.exit(1)
    output_str_file.parent.mkdir(parents=True, exist_ok=True)

    # SAGE expects ANSI/Windows-1252 bytes for Western-language string values.
    try:
        # Newlines are written explicitly below; disable implicit translation.
        f = open(output_str_file, "w", encoding=encoding, newline="")
    except LookupError:
        print(f"Codificación no válida: {encoding}")
        sys.exit(1)

    with f:
        f.write("// String file for Lord of the Rings\r\n\r\n")
        
        for entry in entries:
            entry_id = entry.get("id")
            if not entry_id:
                continue
            if entry_id in excluded_ids or (
                args.exclude_whitespace_ids and not entry_id.strip()
            ):
                excluded_count += 1
                continue
                
            text = entry.get("translation")
            if not text:
                text = entry.get("source") or entry.get("text", "")
                fallback_count += 1
            
            # Escapar comillas dobles internas
            text_escaped = text.replace('"', '\\"')
            
            f.write(f"{entry_id}\r\n")
            try:
                f.write(f'"{text_escaped}"\r\n')
            except UnicodeEncodeError as error:
                print(
                    f"Texto no representable con {encoding} en {entry_id}: "
                    f"{error.object[error.start:error.end]!r}"
                )
                sys.exit(1)
            f.write("END\r\n\r\n")
            compiled_count += 1

    print(f"Build completado: {output_str_file}")
    print(f"Total de entradas compiladas: {compiled_count}")
    if excluded_count:
        print(f"Entradas excluidas de esta build: {excluded_count}")
    if fallback_count:
        print(f"Entradas compiladas con texto fuente: {fallback_count}")
    if deduped_ids:
        print(f"IDs duplicados deduplicados ({args.dedupe_ids}): {len(deduped_ids)}")
        for entry_id in sorted(set(deduped_ids)):
            print(f"  - {entry_id}")


if __name__ == "__main__":
    main()
