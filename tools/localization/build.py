#!/usr/bin/env python3

import json
import sys
from pathlib import Path

from normalize_escapes import normalize_data


def main():
    if len(sys.argv) < 3:
        print("Usage: build.py <catalog.json> <output.str>")
        sys.exit(1)

    catalog_file = Path(sys.argv[1])
    output_str_file = Path(sys.argv[2])
    encoding = "cp1252"
    if "--encoding" in sys.argv[3:]:
        encoding_index = sys.argv.index("--encoding") + 1
        if encoding_index >= len(sys.argv):
            print("Usage: build.py <catalog.json> <output.str> [--encoding ENCODING]")
            sys.exit(1)
        encoding = sys.argv[encoding_index]

    with open(catalog_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    normalized_count = normalize_data(data)
    if normalized_count:
        print(f"Secuencias de escape normalizadas durante el build: {normalized_count}")

    entries = data.get("entries", [])
    output_str_file.parent.mkdir(parents=True, exist_ok=True)

    # SAGE expects ANSI/Windows-1252 bytes for Western-language string values.
    try:
        f = open(output_str_file, "w", encoding=encoding, newline="\r\n")
    except LookupError:
        print(f"Codificación no válida: {encoding}")
        sys.exit(1)

    with f:
        f.write("// String file for Lord of the Rings\r\n\r\n")
        
        for entry in entries:
            entry_id = entry.get("id")
            if not entry_id:
                continue
                
            text = entry.get("translation") or entry.get("source") or entry.get("text", "")
            
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

    print(f"Build completado: {output_str_file}")
    print(f"Total de entradas compiladas: {len(entries)}")


if __name__ == "__main__":
    main()
