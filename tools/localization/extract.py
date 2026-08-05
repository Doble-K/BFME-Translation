#!/usr/bin/env python3

import argparse
import json
import sys
from pathlib import Path


class StringFileError(ValueError):
    """Raised when a SAGE string file contains an invalid block."""


def parse_text(line, line_number):
    normalized_line = line.rstrip()
    if not normalized_line.startswith('"') or not normalized_line.endswith('"'):
        raise StringFileError(f"Línea {line_number}: texto sin comillas completas")

    value = normalized_line[1:-1]
    result = []
    index = 0
    while index < len(value):
        if value[index] == "\\" and index + 1 < len(value) and value[index + 1] == '"':
            result.append('"')
            index += 2
            continue
        result.append(value[index])
        index += 1
    return "".join(result)


def extract_str(path, encoding="cp1252"):
    entries = []
    current_id = None
    current_text = None
    start_line = None

    try:
        with open(path, "r", encoding=encoding, newline=None) as string_file:
            for line_number, raw_line in enumerate(string_file, 1):
                line = raw_line.rstrip("\r\n")

                if current_id is None:
                    if not line.strip() or line.lstrip().startswith("//"):
                        continue
                    if line.strip().upper() == "END":
                        raise StringFileError(f"Línea {line_number}: END sin entrada")
                    current_id = line
                    start_line = line_number
                    continue

                if line.strip().upper() == "END":
                    if current_text is None:
                        raise StringFileError(
                            f"Línea {line_number}: falta el texto para {current_id}"
                        )
                    entries.append({
                        "id": current_id,
                        "text": current_text,
                        "line": start_line,
                    })
                    current_id = None
                    current_text = None
                    start_line = None
                    continue

                if not line.strip():
                    continue

                if line.lstrip().startswith("//"):
                    continue

                if (
                    current_text is None
                    and not current_id.strip()
                    and line.strip()
                    and not line.startswith('"')
                ):
                    current_id = line
                    start_line = line_number
                    continue

                if current_text is not None:
                    raise StringFileError(
                        f"Línea {line_number}: contenido inesperado en {current_id}"
                    )
                current_text = parse_text(line, line_number)
    except UnicodeDecodeError as error:
        raise StringFileError(f"No se pudo decodificar {path} con {encoding}: {error}") from error

    if current_id is not None:
        raise StringFileError(f"Entrada incompleta para {current_id}, falta END")

    return entries


def main():
    parser = argparse.ArgumentParser(description="Extract entries from a SAGE .str file.")
    parser.add_argument("input", help="Input .str file")
    parser.add_argument("output", help="Output JSON catalog")
    parser.add_argument("--encoding", default="cp1252", help="Input encoding")
    args = parser.parse_args()

    try:
        entries = extract_str(args.input, args.encoding)
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", encoding="utf-8", newline="\n") as output_file:
            json.dump(
                {"source": str(args.input), "entries": entries},
                output_file,
                indent=2,
                ensure_ascii=False,
            )
            output_file.write("\n")
    except (OSError, StringFileError, LookupError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    print(f"Extracted {len(entries)} entries")
    print(f"Written: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
