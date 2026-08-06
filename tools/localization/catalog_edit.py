#!/usr/bin/env python3

import argparse
import copy
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from agent_batch import (
    catalog_lock,
    lease_registry_path,
    load_lease_registry,
    prune_leases,
    save_json,
)
from normalize_hotkeys import hotkey_letter, normalize_hotkey_text
from project import load_project, resolve_project_path
from validate_translation import (
    DEFAULT_RULES,
    protected_tokens,
    protected_tokens_match,
)


SYSTEM_ID_PREFIXES = ("LETTER:", "NUMBER:", "Version:")


class CatalogEditError(ValueError):
    pass


class EntryReservedError(CatalogEditError):
    pass


class EntryConflictError(CatalogEditError):
    pass


def entry_revision(entry):
    serialized = json.dumps(
        entry, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.md5(
        serialized.encode("utf-8"), usedforsecurity=False
    ).hexdigest()


def resolve_catalog_path(project_path=None, catalog_path=None):
    if project_path:
        project = load_project(project_path)
        return resolve_project_path(project, "catalog").resolve(strict=True)
    if catalog_path:
        return Path(catalog_path).expanduser().resolve(strict=True)
    raise CatalogEditError("indique project_path o catalog_path")


def load_rules(path=DEFAULT_RULES):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def active_reservations(registry):
    reservations = {}
    for lease in registry.get("leases", []):
        for entry_id in lease.get("entry_ids", []):
            reservations.setdefault(entry_id, []).append({
                "worker": lease.get("worker"),
                "batch_id": lease.get("batch_id"),
                "expires_at": lease.get("expires_at"),
            })
    return reservations


def catalog_snapshot(project_path=None, catalog_path=None):
    path = resolve_catalog_path(project_path, catalog_path)
    registry_path = lease_registry_path(path)
    with catalog_lock(path):
        data = json.loads(path.read_text(encoding="utf-8"))
        registry = load_lease_registry(registry_path, path)
        prune_leases(registry)
    return data, active_reservations(registry)


def entry_view(entry, reservations=None):
    reservations = reservations or []
    return {
        "id": entry.get("id"),
        "source": entry.get("source", ""),
        "translation": entry.get("translation", ""),
        "status": entry.get("status"),
        "flags": list(entry.get("flags", [])),
        "notes": entry.get("notes", ""),
        "entry_revision": entry_revision(entry),
        "reserved": bool(reservations),
        "reservations": copy.deepcopy(reservations),
    }


def search_entries(
    project_path=None,
    catalog_path=None,
    query="",
    statuses=None,
    limit=200,
    include_system=False,
):
    if not 1 <= limit <= 1000:
        raise CatalogEditError("limit debe estar entre 1 y 1000")
    data, reservations = catalog_snapshot(project_path, catalog_path)
    query = query.casefold().strip()
    selected = []
    effective = {}
    for entry in data.get("entries", []):
        entry_id = entry.get("id")
        if (
            not isinstance(entry_id, str)
            or not entry_id.strip()
            or not entry.get("duplicate_meta", {}).get("selected", True)
            or "orphan_meta" in entry
        ):
            continue
        effective[entry_id] = entry

    for entry in effective.values():
        entry_id = entry["id"]
        if not include_system and entry_id.startswith(SYSTEM_ID_PREFIXES):
            continue
        if statuses and entry.get("status") not in statuses:
            continue
        if query and not any(
            query in str(value).casefold()
            for value in (
                entry_id,
                entry.get("source", ""),
                entry.get("translation", ""),
            )
        ):
            continue
        selected.append(entry_view(entry, reservations.get(entry_id)))
        if len(selected) == limit:
            break
    return selected


def find_entry(data, entry_id, expected_revision):
    matching_id = []
    for entry in data.get("entries", []):
        if entry.get("id") != entry_id:
            continue
        matching_id.append(entry)
        if entry_revision(entry) == expected_revision:
            return entry
    if matching_id:
        raise EntryConflictError(
            f"{entry_id}: la entrada cambió desde que fue abierta; recárguela"
        )
    raise CatalogEditError(f"{entry_id}: la entrada no existe")


def add_flag(entry, flag):
    flags = entry.setdefault("flags", [])
    if flag not in flags:
        flags.append(flag)


def remove_flag(entry, flag):
    entry.setdefault("flags", [])
    entry["flags"] = [current for current in entry["flags"] if current != flag]


def validate_and_normalize(entry, translation, rules):
    if not isinstance(translation, str) or not translation.strip():
        raise CatalogEditError("la traducción no puede estar vacía")
    source = entry.get("source", "")
    if translation == source:
        raise CatalogEditError(
            "la traducción coincide con la fuente; use la acción preserve"
        )
    if not protected_tokens_match(source, translation, rules):
        raise CatalogEditError(
            f"tokens inválidos; esperado {protected_tokens(source, rules)}, "
            f"recibido {protected_tokens(translation, rules)}"
        )
    letter = hotkey_letter(source) or hotkey_letter(translation)
    normalized = normalize_hotkey_text(translation, letter) if letter else translation
    if not protected_tokens_match(source, normalized, rules):
        raise CatalogEditError("la normalización de hotkeys produjo tokens inválidos")
    return normalized


def record_human_review(entry, timestamp, actor):
    entry.setdefault("review", {}).setdefault("human", {})
    entry["review"]["human"].update({
        "checked": True,
        "user": actor,
        "date": timestamp,
    })


def commit_entry(
    entry_id,
    expected_revision,
    action,
    project_path=None,
    catalog_path=None,
    translation=None,
    mark_reviewed=False,
    actor="human",
    rules_path=DEFAULT_RULES,
):
    path = resolve_catalog_path(project_path, catalog_path)
    rules = load_rules(rules_path)
    registry_path = lease_registry_path(path)

    with catalog_lock(path):
        data = json.loads(path.read_text(encoding="utf-8"))
        registry = load_lease_registry(registry_path, path)
        prune_leases(registry)
        reservations = active_reservations(registry).get(entry_id, [])
        if reservations:
            workers = ", ".join(
                sorted({item.get("worker") or "desconocido" for item in reservations})
            )
            raise EntryReservedError(
                f"{entry_id}: entrada reservada por {workers}; espere o detenga ese lote"
            )

        entry = find_entry(data, entry_id, expected_revision)
        old_translation = entry.get("translation", "")
        old_status = entry.get("status")
        timestamp = datetime.now(timezone.utc).isoformat()

        if action == "save":
            normalized = validate_and_normalize(entry, translation, rules)
            entry["translation"] = normalized
            entry["status"] = "reviewed" if mark_reviewed else "translated"
            entry.setdefault("translation_meta", {}).update({
                "origin": "human",
                "model": None,
                "date": timestamp,
                "confidence": 1.0,
            })
            if mark_reviewed:
                remove_flag(entry, "needs_review")
                record_human_review(entry, timestamp, actor)
            else:
                add_flag(entry, "needs_review")
            history_action = "translated" if not old_translation else "edited"
        elif action == "review":
            if not old_translation:
                raise CatalogEditError(f"{entry_id}: no hay traducción para revisar")
            if not protected_tokens_match(entry.get("source", ""), old_translation, rules):
                raise CatalogEditError(f"{entry_id}: la traducción tiene tokens inválidos")
            entry["status"] = "reviewed"
            remove_flag(entry, "needs_review")
            record_human_review(entry, timestamp, actor)
            history_action = "reviewed"
        elif action == "requeue":
            entry["translation"] = ""
            entry["status"] = "pending"
            add_flag(entry, "needs_review")
            add_flag(entry, "manual_requeue")
            entry["translation_meta"] = {
                "origin": None,
                "model": None,
                "date": timestamp,
                "confidence": 0.0,
            }
            history_action = "returned_to_queue"
        elif action == "preserve":
            entry["translation"] = entry.get("source", "")
            entry["status"] = "preserved"
            remove_flag(entry, "needs_review")
            add_flag(entry, "source_preserved")
            entry.setdefault("translation_meta", {}).update({
                "origin": "human_preserved",
                "model": None,
                "date": timestamp,
                "confidence": 1.0,
            })
            history_action = "source_preserved"
        else:
            raise CatalogEditError(f"acción desconocida: {action}")

        entry.setdefault("history", []).append({
            "date": timestamp,
            "action": history_action,
            "from": old_translation if action != "review" else old_status,
            "to": entry.get("translation", "") if action != "review" else entry["status"],
            "by": actor,
        })
        save_json(path, data)
        return entry_view(entry)


def add_catalog_argument_group(parser):
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--project", type=Path)
    group.add_argument("--catalog", type=Path)


def main():
    parser = argparse.ArgumentParser(
        description="Safely inspect and edit individual localization entries."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list")
    add_catalog_argument_group(list_parser)
    list_parser.add_argument("--query", default="")
    list_parser.add_argument("--status", action="append", dest="statuses")
    list_parser.add_argument("--limit", type=int, default=200)
    list_parser.add_argument("--include-system", action="store_true")

    for command in ("save", "review", "requeue", "preserve"):
        command_parser = subparsers.add_parser(command)
        add_catalog_argument_group(command_parser)
        command_parser.add_argument("--id", required=True, dest="entry_id")
        command_parser.add_argument("--expected-revision", required=True)
        command_parser.add_argument("--actor", default="human")
        if command == "save":
            command_parser.add_argument("--translation", required=True)
            command_parser.add_argument("--mark-reviewed", action="store_true")

    args = parser.parse_args()
    try:
        target = {
            "project_path": args.project,
            "catalog_path": args.catalog,
        }
        if args.command == "list":
            result = search_entries(
                **target,
                query=args.query,
                statuses=set(args.statuses or []),
                limit=args.limit,
                include_system=args.include_system,
            )
        else:
            result = commit_entry(
                args.entry_id,
                args.expected_revision,
                args.command,
                **target,
                translation=getattr(args, "translation", None),
                mark_reviewed=getattr(args, "mark_reviewed", False),
                actor=args.actor,
            )
    except (CatalogEditError, OSError, json.JSONDecodeError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
