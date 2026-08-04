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

    # El motor SAGE de BFME requiere estrictamente UTF-16 con BOM y saltos de línea CRLF (\r\n)
    with open(output_str_file, "w", encoding="utf-16", newline="\r\n") as f:
        for entry in entries:
            entry_id = entry.get("id")
            if not entry_id:
                continue
                
            text = entry.get("translation") or entry.get("source") or entry.get("text", "")
            
            # Escapar comillas dobles internas para que el parser no rompa la línea
            text_escaped = text.replace('"', '\\"')
            
            # Estructura clásica exacta que espera el parser de los .str de EA
            f.write(f"{entry_id}\r\n")
            f.write(f'"{text_escaped}"\r\n')
            f.write("END\r\n\r\n")

    print(f"Build completado: {output_str_file}")
    print(f"Total de entradas compiladas: {len(entries)}")


if __name__ == "__main__":
    main()
