#!/usr/bin/env python3

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

from project import load_project, resolve_project_path
from validate_translation import DEFAULT_RULES, protected_tokens


ROOT = Path(__file__).resolve().parents[2]


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


def load_fixture(path):
    with path.open(encoding="utf-8") as fixture_file:
        fixture = json.load(fixture_file)
    if not isinstance(fixture, dict):
        raise ValueError("El fixture debe ser un objeto JSON")
    return fixture


def select_entries(data, mode, count):
    if mode == "translate":
        eligible = (
            entry for entry in data.get("entries", [])
            if entry.get("status") == "pending"
            and isinstance(entry.get("source"), str)
            and bool(entry["source"])
            and entry.get("duplicate_meta", {}).get("selected", True)
            and "orphan_meta" not in entry
        )
    else:
        eligible = (
            entry for entry in data.get("entries", [])
            if entry.get("status") == "translated"
            and "needs_review" in entry.get("flags", [])
        )
    return list(eligible)[:count]


def fixture_translation(fixture, entry_id):
    translations = fixture.get("translations", {})
    if not isinstance(translations, dict) or entry_id not in translations:
        raise ValueError(f"El fixture no contiene traducción para {entry_id}")
    value = translations[entry_id]
    if not isinstance(value, str) or not value:
        raise ValueError(f"La traducción del fixture es inválida para {entry_id}")
    return value


def fixture_review(fixture, entry_id):
    reviews = fixture.get("reviews", {})
    if not isinstance(reviews, dict) or entry_id not in reviews:
        raise ValueError(f"El fixture no contiene revisión para {entry_id}")
    review = reviews[entry_id]
    if not isinstance(review, dict):
        raise ValueError(f"La revisión del fixture es inválida para {entry_id}")
    issues = review.get("issues", [])
    suggestion = review.get("suggestion")
    confidence = review.get("confidence")
    if not isinstance(issues, list) or not all(isinstance(issue, str) for issue in issues):
        raise ValueError(f"Los issues del fixture son inválidos para {entry_id}")
    if suggestion is not None and not isinstance(suggestion, str):
        raise ValueError(f"La sugerencia del fixture es inválida para {entry_id}")
    if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
        raise ValueError(f"La confianza del fixture es inválida para {entry_id}")
    return {"issues": issues, "suggestion": suggestion, "confidence": confidence}


def parse_model_json(content):
    content = content.strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    result = json.loads(content)
    if not isinstance(result, dict):
        raise ValueError("La respuesta del modelo debe ser un objeto JSON")
    return result


def ollama_response(url, model, mode, entries, glossary, language, timeout):
    if mode == "translate":
        output_schema = '{"translations":[{"id":"...","translation":"..."}]}'
        task = "Translate every source string into the target language."
    else:
        output_schema = '{"reviews":[{"id":"...","issues":[],"suggestion":null,"confidence":0.0}]}'
        task = "Review every current translation for meaning, terminology, and context."
    input_entries = [
        {
            "id": entry["id"],
            "source": entry.get("source", ""),
            "translation": entry.get("translation", ""),
        }
        for entry in entries
    ]
    system = (
        "You are a localization assistant. Return JSON only, with no markdown. "
        "Never change IDs. Preserve every protected token exactly. "
        f"Target language: {language}. Output schema: {output_schema}"
    )
    prompt = json.dumps({
        "task": task,
        "entries": input_entries,
        "glossary": glossary,
    }, ensure_ascii=False)
    payload = json.dumps({
        "model": model,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
    }).encode("utf-8")
    request = urllib.request.Request(
        f"{url.rstrip('/')}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as error:
        raise ValueError(f"No se pudo consultar Ollama: {error}") from error
    try:
        return parse_model_json(body["message"]["content"])
    except (KeyError, TypeError, json.JSONDecodeError) as error:
        raise ValueError(f"Respuesta JSON inválida de Ollama: {error}") from error


def main():
    parser = argparse.ArgumentParser(
        description="Run reproducible bulk AI translation or review jobs."
    )
    parser.add_argument("--project", required=True, help="Project configuration JSON")
    parser.add_argument("--mode", choices=("translate", "review"), required=True)
    parser.add_argument("--provider", choices=("fixture", "ollama"), default="fixture")
    parser.add_argument("--fixture", help="Fixture JSON provider response")
    parser.add_argument("--count", type=int, default=50)
    parser.add_argument("--dry-run", action="store_true", help="Do not write catalog changes")
    parser.add_argument("--write", action="store_true", help="Write results to the catalog")
    parser.add_argument("--model", default="fixture", help="Model/provider label in metadata")
    parser.add_argument("--actor", default="ai", help="Actor recorded in metadata")
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--rules", type=Path, default=DEFAULT_RULES)
    parser.add_argument(
        "--glossary",
        type=Path,
        default=ROOT / "GLOSSARY.md",
        help="Glossary supplied as provider context",
    )
    args = parser.parse_args()

    if args.count < 1:
        parser.error("--count debe ser mayor que cero")
    if args.provider == "fixture" and not args.fixture:
        parser.error("--fixture es obligatorio con --provider fixture")
    if args.write and args.dry_run:
        parser.error("--write y --dry-run son incompatibles")

    try:
        project = load_project(args.project)
        catalog_path = resolve_project_path(project, "catalog")
        fixture = load_fixture(Path(args.fixture)) if args.provider == "fixture" else None
        rules = json.loads(args.rules.read_text(encoding="utf-8"))
        glossary = args.glossary.read_text(encoding="utf-8")
    except (OSError, json.JSONDecodeError, ValueError) as error:
        print(f"Error: no se pudo cargar el trabajo bulk: {error}", file=sys.stderr)
        return 1

    data = json.loads(catalog_path.read_text(encoding="utf-8"))
    entries = select_entries(data, args.mode, args.count)
    if not entries:
        print("No hay entradas elegibles para este lote.")
        return 0

    today = datetime.now().strftime("%Y-%m-%d")
    results = []
    try:
        if args.provider == "ollama":
            provider_result = ollama_response(
                args.ollama_url,
                args.model,
                args.mode,
                entries,
                glossary,
                project["language"],
                args.timeout,
            )
        else:
            provider_result = fixture
        if args.mode == "translate":
            provider_items = provider_result.get("translations", [])
            if args.provider == "fixture":
                provider_translations = provider_items if isinstance(provider_items, dict) else {}
            else:
                if not isinstance(provider_items, list):
                    raise ValueError("La respuesta no contiene una lista translations")
                provider_translations = {
                    item.get("id"): item.get("translation")
                    for item in provider_items
                    if isinstance(item, dict)
                }
        for entry in entries:
            entry_id = entry["id"]
            if args.mode == "translate":
                translation = (
                    fixture_translation(provider_result, entry_id)
                    if args.provider == "fixture"
                    else provider_translations.get(entry_id)
                )
                if not isinstance(translation, str) or not translation:
                    raise ValueError(f"La respuesta del proveedor no contiene {entry_id}")
                expected = protected_tokens(entry["source"], rules)
                actual = protected_tokens(translation, rules)
                if expected != actual:
                    raise ValueError(
                        f"TOKEN ERROR {entry_id}: expected {expected}, received {actual}"
                    )
                results.append((entry, translation))
            else:
                review = fixture_review(provider_result, entry_id)
                if review["suggestion"]:
                    expected = protected_tokens(entry["source"], rules)
                    actual = protected_tokens(review["suggestion"], rules)
                    if expected != actual:
                        raise ValueError(
                            f"TOKEN ERROR {entry_id}: review suggestion has invalid tokens"
                        )
                results.append((entry, review))
    except ValueError as error:
        print(f"Error: lote rechazado sin modificar el catálogo: {error}", file=sys.stderr)
        return 1

    print(f"Modo: {args.mode}")
    print(f"Entradas seleccionadas: {len(entries)}")
    print(f"Glosario cargado: {len(glossary)} caracteres")
    if not args.write:
        print("Dry-run: no se modificó el catálogo.")
        return 0

    for entry, result in results:
        entry.setdefault("flags", [])
        entry.setdefault("translation_meta", {})
        if args.mode == "translate":
            entry["translation"] = result
            entry["status"] = "translated"
            if "needs_review" not in entry["flags"]:
                entry["flags"].append("needs_review")
            entry["translation_meta"].update({
                "origin": "ai",
                "model": args.model,
                "date": today,
                "confidence": 0.0,
            })
        else:
            entry.setdefault("review", {}).setdefault("ai", {})
            entry["review"]["ai"].update({
                "checked": True,
                "issues": result["issues"],
                "suggestion": result["suggestion"],
                "confidence": result["confidence"],
                "last_review": today,
                "model": args.model,
                "actor": args.actor,
            })

    try:
        save_catalog(catalog_path, data)
    except OSError as error:
        print(f"Error: no se pudo guardar el lote: {error}", file=sys.stderr)
        return 1

    print(f"Catálogo actualizado: {catalog_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
