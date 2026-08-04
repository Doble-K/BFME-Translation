import sys


def parse_str(path):
    entries = []

    with open(path, "r", encoding="utf-8") as file:
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
    result = parse_str(sys.argv[1])

    print(f"Entries: {len(result)}")

    for item in result[:20]:
        print(item)
