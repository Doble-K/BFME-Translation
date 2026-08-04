#!/usr/bin/env python3

import json
import sys
from pathlib import Path


def main():
    if len(sys.argv) < 3:
        print("Usage: build.py <catalog.json> <output.str>")
        sys.exit(1)

    catalog_file = Path(sys.argv[1])
    output_str_file = Path(sys.argv[2])

    with open(catalog_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    entries = data.get("entries", [])
    output_str_file.parent.mkdir(parents=True, exist_ok=True)

    # Escribir en UTF-8 con saltos de línea de Windows (CRLF), igual que el original
    with open(output_str_file, "w", encoding="utf-8", newline="\r\n") as f:
        f.write("// String file for Lord of the Rings\r\n\r\n")
        
        for entry in entries:
            entry_id = entry.get("id")
            if not entry_id:
                continue
                
            text = entry.get("translation") or entry.get("source") or entry.get("text", "")
            
            # Escapar comillas dobles internas
            text_escaped = text.replace('"', '\\"')
            
            f.write(f"{entry_id}\r\n")
            f.write(f'"{text_escaped}"\r\n')
            f.write("END\r\n\r\n")

    print(f"Build completado: {output_str_file}")
    print(f"Total de entradas compiladas: {len(entries)}")


if __name__ == "__main__":
    main()
