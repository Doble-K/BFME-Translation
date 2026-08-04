#!/usr/bin/env python3

import json
import sys

def main():
    if len(sys.argv) != 3:
        print("Usage: export_str.py <catalog.json> <output.str>")
        sys.exit(1)

    catalog_file = sys.argv[1]
    output_str_file = sys.argv[2]

    with open(catalog_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    entries = data.get("entries", [])

    # Formato estándar de los archivos .str de BFME
    # Generalmente usan codificación UTF-16 con BOM (o UTF-8 con BOM según el parche/motor de Open-BFME1)
    with open(output_str_file, "w", encoding="utf-16") as f:
        f.write("StringFileInfo\n{\n")
        
        for entry in entries:
            entry_id = entry["id"]
            # Si tiene traducción la usa, si no, cae en el source original por seguridad
            text = entry.get("translation") or entry["source"]
            
            # Escapar saltos de línea o comillas si el motor lo requiere
            text_escaped = text.replace('"', '\\"')
            
            f.write(f'    "{entry_id}" "{text_escaped}"\n')
            
        f.write("}\n")

    print(f"Exportación completada con éxito: {output_str_file}")
    print(f"Total de cadenas exportadas: {len(entries)}")

if __name__ == "__main__":
    main()
