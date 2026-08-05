import sys


def parse_str(path, encoding="cp1252"):
    entries = []

    with open(path, "r", encoding=encoding) as file:
        lines = file.readlines()

    current_key = None

    for line in lines:
        line = line.rstrip("\n")

        if line == "END":
            current_key = None
            continue

        if current_key is None and ":" in line and not line.startswith("//"):
            current_key = line
            entries.append(current_key)

    return entries


if __name__ == "__main__":
    encoding = sys.argv[2] if len(sys.argv) > 2 else "cp1252"
    result = parse_str(sys.argv[1], encoding)

    print(f"Entries: {len(result)}")

    for item in result[:20]:
        print(item)
