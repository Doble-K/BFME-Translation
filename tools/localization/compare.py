import json
import sys


def load(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    return {
        e["id"]: e["text"]
        for e in data["entries"]
    }


english = load(sys.argv[1])
spanish = load(sys.argv[2])


missing = []
same = []
extra = []


for key, value in english.items():
    if key not in spanish:
        missing.append(key)
    elif spanish[key] == value:
        same.append({
            "id": key,
            "text": value
        })


for key in spanish:
    if key not in english:
        extra.append(key)


result = {
    "english_entries": len(english),
    "spanish_entries": len(spanish),
    "missing_in_spanish": missing,
    "same_as_english": same,
    "extra_in_spanish": extra
}


with open(
    "reports/generated/spanish_report.json",
    "w",
    encoding="utf-8"
) as f:
    json.dump(result, f, indent=2, ensure_ascii=False)


print("English:", len(english))
print("Spanish:", len(spanish))
print("Missing:", len(missing))
print("Same:", len(same))
print("Extra:", len(extra))
