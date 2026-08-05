#!/usr/bin/env python3

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

from project import load_project, resolve_project_path
from validate_translation import DEFAULT_RULES, protected_tokens, protected_tokens_match
from normalize_hotkeys import hotkey_letter, normalize_hotkey_text


ROOT = Path(__file__).resolve().parents[2]
SYSTEM_ID_PREFIXES = ("LETTER:", "NUMBER:", "Version:")
URL_PATTERN = re.compile(r"https?://\S+", re.IGNORECASE)
HOTKEY_TOKEN_PATTERN = re.compile(r"\[&([^\s])\]|&([^\s])")
SAGE_ESCAPES = (("\n", r"\n"), ("\t", r"\t"), ("\r", r"\r"))


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
            and not entry.get("id", "").startswith(SYSTEM_ID_PREFIXES)
            and entry.get("duplicate_meta", {}).get("selected", True)
            and "orphan_meta" not in entry
        )
    else:
        eligible = (
            entry for entry in data.get("entries", [])
            if entry.get("status") == "translated"
            and "needs_review" in entry.get("flags", [])
        )
    selected = []
    seen_ids = set()
    for entry in reversed(list(eligible)):
        entry_id = entry.get("id")
        if entry_id in seen_ids:
            continue
        seen_ids.add(entry_id)
        selected.append(entry)
        if len(selected) >= count:
            break
    return list(reversed(selected))


def choose_model(entry, routing, small_model, large_model, long_chars, rules):
    if routing == "single":
        return small_model
    source = entry.get("source", "")
    complex_id = any(
        marker in entry.get("id", "")
        for marker in ("Description", "Desc", "Ability", "Power", "ToolTip")
    )
    has_many_lines = source.count(r"\n") >= 2 or source.count("\n") >= 2
    has_many_tokens = len(protected_tokens(source, rules)) >= 3
    if len(source) > long_chars or has_many_lines or has_many_tokens or complex_id:
        return large_model
    return small_model


def order_entries_by_model(entries, routing, small_model, large_model, long_chars, rules):
    if routing == "single":
        return entries
    return sorted(
        entries,
        key=lambda entry: choose_model(
            entry, routing, small_model, large_model, long_chars, rules
        ) != small_model,
    )


def mask_protected_tokens(source, rules):
    masked = source
    replacements = []
    for index, token in enumerate(protected_tokens(source, rules)):
        placeholder = f"__SAGE_TOKEN_{index}__"
        masked = masked.replace(token, placeholder, 1)
        replacements.append((placeholder, token))
    return masked, replacements


def restore_protected_tokens(value, replacements):
    for placeholder, token in replacements:
        value = value.replace(placeholder, token)
    return value


def remove_hotkeys(source):
    hotkeys = []

    def strip_hotkey(match):
        hotkeys.append(match.group(0))
        return "" if match.group(0).startswith("[") else (match.group(1) or match.group(2))

    pieces = []
    cursor = 0
    for url_match in URL_PATTERN.finditer(source):
        segment = source[cursor:url_match.start()]
        pieces.append(HOTKEY_TOKEN_PATTERN.sub(strip_hotkey, segment))
        pieces.append(url_match.group(0))
        cursor = url_match.end()
    pieces.append(HOTKEY_TOKEN_PATTERN.sub(strip_hotkey, source[cursor:]))
    return "".join(pieces), hotkeys


def restore_hotkeys(value, hotkeys):
    for hotkey in hotkeys:
        if hotkey not in value:
            value = f"{value.rstrip()} {hotkey}"
    return value


def normalize_sage_escapes(source, value):
    for actual, escaped in SAGE_ESCAPES:
        if escaped in source:
            value = value.replace(actual, escaped)
    return value


def normalize_ai_translation(source, value):
    value = normalize_sage_escapes(source, value)
    letter = hotkey_letter(source) or hotkey_letter(value)
    return normalize_hotkey_text(value, letter) if letter else value


def apply_ai_result(entry, result, model, mode, today, actor):
    entry.setdefault("flags", [])
    entry.setdefault("translation_meta", {})
    if mode == "translate":
        entry["translation"] = result
        entry["status"] = "translated"
        if "needs_review" not in entry["flags"]:
            entry["flags"].append("needs_review")
        entry["translation_meta"].update({
            "origin": "ai",
            "model": model,
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
            "model": model,
            "actor": actor,
        })


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


def ollama_response(url, model, mode, entries, glossary, language, timeout, feedback=None, rules=None):
    if mode == "translate":
        output_schema = '{"translations":[{"key":"...","translation":"..."}]}'
        task = "Translate every source string into the target language."
    else:
        output_schema = '{"reviews":[{"key":"...","issues":[],"suggestion":null,"confidence":0.0}]}'
        task = "Review every current translation for meaning, terminology, and context."
    token_replacements = []
    input_entries = []
    for index, entry in enumerate(entries):
        source_without_hotkeys, hotkeys = remove_hotkeys(entry.get("source", ""))
        source, replacements = mask_protected_tokens(source_without_hotkeys, rules or {})
        token_replacements.append((replacements, hotkeys))
        input_entries.append({
            "key": f"item_{index}",
            "source": source,
            "translation": entry.get("translation", ""),
            "protected_tokens": protected_tokens(entry.get("source", ""), rules or {}),
            "protected_placeholders": [placeholder for placeholder, _ in replacements],
            "hotkeys_restored_automatically": hotkeys,
        })
    system = (
        "You are a localization assistant. Return JSON only, with no markdown. "
        "Keys are opaque and must be copied character-for-character; never invent or translate them. "
        "Do not output engine IDs. Preserve every protected token exactly; every protected placeholder "
        "listed for an entry must appear in its translation exactly once. Hotkeys are restored automatically "
        "at the end; do not invent, move, or translate them. Do not replace placeholders with newlines or "
        "other text. "
        f"Target language: {language}. Output schema: {output_schema}. "
        "Examples: source '1 Second' returns '1 segundo'; source '%d Days' with token ['%d'] "
        "returns '%d Días'."
    )
    prompt = json.dumps({
        "task": task,
        "entries": input_entries,
        "glossary": glossary,
        "previous_error": feedback,
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
        result = parse_model_json(body["message"]["content"])
        if mode == "translate":
            for index, item in enumerate(result.get("translations", [])):
                if index < len(token_replacements) and isinstance(item, dict):
                    item["translation"] = normalize_sage_escapes(
                        entries[index].get("source", ""),
                        restore_protected_tokens(
                        item.get("translation", ""), token_replacements[index][0]
                        ),
                    )
                    item["translation"] = restore_hotkeys(item["translation"], token_replacements[index][1])
        else:
            for index, item in enumerate(result.get("reviews", [])):
                if index < len(token_replacements) and isinstance(item, dict):
                    suggestion = item.get("suggestion")
                    if isinstance(suggestion, str):
                        item["suggestion"] = normalize_sage_escapes(
                            entries[index].get("source", ""),
                            restore_protected_tokens(
                            suggestion, token_replacements[index][0]
                            ),
                        )
                        item["suggestion"] = restore_hotkeys(item["suggestion"], token_replacements[index][1])
        return result
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
    parser.add_argument("--retries", type=int, choices=range(1, 6), default=3)
    parser.add_argument("--dry-run", action="store_true", help="Do not write catalog changes")
    parser.add_argument("--write", action="store_true", help="Write results to the catalog")
    parser.add_argument(
        "--checkpoint",
        action="store_true",
        help="Save each successful result immediately; requires --write",
    )
    parser.add_argument("--model", default="fixture", help="Model/provider label in metadata")
    parser.add_argument("--routing", choices=("single", "auto"), default="single")
    parser.add_argument("--small-model", default="llama3.2:3b")
    parser.add_argument("--large-model", default="qwen2.5:7b")
    parser.add_argument("--long-chars", type=int, default=180)
    parser.add_argument("--actor", default="ai", help="Actor recorded in metadata")
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument(
        "--max-seconds",
        type=float,
        default=0,
        help="Stop the batch after this many seconds; 0 means no total limit",
    )
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
    if args.checkpoint and not args.write:
        parser.error("--checkpoint requiere --write")
    if args.max_seconds < 0:
        parser.error("--max-seconds no puede ser negativo")

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
    entries = order_entries_by_model(
        entries,
        args.routing,
        args.small_model,
        args.large_model,
        args.long_chars,
        rules,
    )
    if not entries:
        print("No hay entradas elegibles para este lote.")
        return 0
    print(f"BATCH {len(entries)}", flush=True)

    today = datetime.now().strftime("%Y-%m-%d")
    results = []
    skipped = []
    checkpointed = set()
    model_counts = {}
    deadline = time.monotonic() + args.max_seconds if args.max_seconds else None
    timed_out = False
    for entry_index, entry in enumerate(entries, 1):
        if deadline and time.monotonic() >= deadline:
            timed_out = True
            print("Tiempo máximo alcanzado; se detiene el lote.")
            break
        entry_id = entry["id"]
        model = (
            choose_model(
                entry,
                args.routing,
                args.small_model,
                args.large_model,
                args.long_chars,
                rules,
            )
            if args.provider == "ollama"
            else args.model
        )
        model_counts[model] = model_counts.get(model, 0) + 1
        print(
            "ENTRY " + json.dumps({
                "current": entry_index,
                "total": len(entries),
                "id": entry_id,
                "model": model,
                "source": entry.get("source", ""),
            }, ensure_ascii=False),
            flush=True,
        )
        last_error = None
        for attempt in range(1, args.retries + 1):
            try:
                request_timeout = args.timeout
                if deadline:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        timed_out = True
                        break
                    request_timeout = min(request_timeout, max(1, int(remaining)))
                provider_result = (
                    ollama_response(
                        args.ollama_url,
                        model,
                        args.mode,
                        [entry],
                        glossary,
                        project["language"],
                        request_timeout,
                        feedback=str(last_error) if last_error else None,
                        rules=rules,
                    )
                    if args.provider == "ollama"
                    else fixture
                )
                if args.mode == "translate":
                    if args.provider == "fixture":
                        translation = fixture_translation(provider_result, entry_id)
                    else:
                        provider_items = provider_result.get("translations", [])
                        if not isinstance(provider_items, list):
                            raise ValueError("La respuesta no contiene una lista translations")
                        matches = [
                            item for item in provider_items
                            if isinstance(item, dict) and item.get("key") == "item_0"
                        ]
                        if len(matches) != 1:
                            raise ValueError(f"La respuesta del proveedor no contiene la clave opaca de {entry_id}")
                        translation = matches[0].get("translation")
                    if not isinstance(translation, str) or not translation:
                        raise ValueError(f"La traducción es inválida para {entry_id}")
                    expected = protected_tokens(entry["source"], rules)
                    actual = protected_tokens(translation, rules)
                    if not protected_tokens_match(entry["source"], translation, rules):
                        raise ValueError(
                            f"TOKEN ERROR {entry_id}: expected {expected}, received {actual}"
                        )
                    translation = normalize_hotkey_text(
                        translation, hotkey_letter(entry.get("source", "")) or hotkey_letter(translation)
                    )
                    results.append((entry, translation, model))
                    if args.checkpoint:
                        apply_ai_result(entry, translation, model, args.mode, today, args.actor)
                        try:
                            save_catalog(catalog_path, data)
                        except OSError as error:
                            raise ValueError(f"No se pudo guardar el checkpoint: {error}") from error
                        checkpointed.add(entry_id)
                    print(
                        "RESULT " + json.dumps({
                            "current": entry_index,
                            "total": len(entries),
                            "id": entry_id,
                            "model": model,
                            "source": entry.get("source", ""),
                            "translation": translation,
                        }, ensure_ascii=False),
                        flush=True,
                    )
                    print(f"PROGRESS {entry_index}/{len(entries)} OK {entry_id} model={model}", flush=True)
                else:
                    if args.provider == "ollama":
                        provider_items = provider_result.get("reviews", [])
                        if not isinstance(provider_items, list):
                            raise ValueError("La respuesta no contiene una lista reviews")
                        matches = [
                            item for item in provider_items
                            if isinstance(item, dict) and item.get("key") == "item_0"
                        ]
                        if len(matches) != 1:
                            raise ValueError(f"La respuesta del proveedor no contiene la clave opaca de {entry_id}")
                        review = {
                            "issues": matches[0].get("issues", []),
                            "suggestion": matches[0].get("suggestion"),
                            "confidence": matches[0].get("confidence"),
                        }
                    else:
                        review = fixture_review(provider_result, entry_id)
                    if review["suggestion"]:
                        expected = protected_tokens(entry["source"], rules)
                        actual = protected_tokens(review["suggestion"], rules)
                        if not protected_tokens_match(entry["source"], review["suggestion"], rules):
                            raise ValueError(
                                f"TOKEN ERROR {entry_id}: review suggestion has invalid tokens"
                            )
                        review["suggestion"] = normalize_hotkey_text(
                            review["suggestion"],
                            hotkey_letter(entry.get("source", "")) or hotkey_letter(review["suggestion"]),
                        )
                    results.append((entry, review, model))
                    if args.checkpoint:
                        apply_ai_result(entry, review, model, args.mode, today, args.actor)
                        try:
                            save_catalog(catalog_path, data)
                        except OSError as error:
                            raise ValueError(f"No se pudo guardar el checkpoint: {error}") from error
                        checkpointed.add(entry_id)
                    print(
                        "RESULT " + json.dumps({
                            "current": entry_index,
                            "total": len(entries),
                            "id": entry_id,
                            "model": model,
                            "source": entry.get("source", ""),
                            "translation": review.get("suggestion") or "(sin sugerencia)",
                        }, ensure_ascii=False),
                        flush=True,
                    )
                    print(f"PROGRESS {entry_index}/{len(entries)} OK {entry_id} model={model}", flush=True)
                last_error = None
                break
            except (ValueError, KeyError, TypeError) as error:
                last_error = error
                print(f"{entry_id}: intento {attempt}/{args.retries} fallido: {error}")
        if last_error:
            skipped.append(entry_id)
            print(f"{entry_id}: omitida sin modificar el catálogo.")
            print(f"PROGRESS {entry_index}/{len(entries)} SKIP {entry_id}", flush=True)
        if timed_out:
            break

    print(f"Modo: {args.mode}")
    print(f"Entradas seleccionadas: {len(entries)}")
    print(f"Entradas exitosas: {len(results)}")
    print(f"Entradas omitidas: {len(skipped)}")
    print(f"Modelos seleccionados: {model_counts}")
    if timed_out:
        print("Lote detenido por límite de tiempo.")
    print(f"Glosario cargado: {len(glossary)} caracteres")
    if not args.write:
        print("Dry-run: no se modificó el catálogo.")
        return 0

    for entry, result, model in results:
        if entry["id"] not in checkpointed:
            apply_ai_result(entry, result, model, args.mode, today, args.actor)

    try:
        save_catalog(catalog_path, data)
    except OSError as error:
        print(f"Error: no se pudo guardar el lote: {error}", file=sys.stderr)
        return 1

    print(f"Catálogo actualizado: {catalog_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
