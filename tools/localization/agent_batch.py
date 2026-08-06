#!/usr/bin/env python3

import argparse
import hashlib
import json
import os
import re
import sys
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from normalize_hotkeys import hotkey_letter, normalize_hotkey_text
from project import load_project, resolve_project_path
from validate_translation import DEFAULT_RULES, protected_tokens, protected_tokens_match


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_VERSION = 3
RESPONSE_SCHEMA_VERSION = 1
LEASE_SCHEMA_VERSION = 1
DEFAULT_LEASE_SECONDS = 21600
SYSTEM_ID_PREFIXES = ("LETTER:", "NUMBER:", "Version:")
WORKER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
WORKER_SCOPE_PREFIX_ENV = "BFME_TRANSLATION_WORKER_PREFIX"
WORKER_SCOPE_COUNT_ENV = "BFME_TRANSLATION_WORKER_COUNT"


def source_hash(entry_id, source):
    value = json.dumps([entry_id, source], ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def entry_hash(entry):
    serialized = json.dumps(entry, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def value_hash(value):
    serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(f".{path.name}.tmp")
    try:
        with temporary_path.open("w", encoding="utf-8", newline="\n") as output_file:
            json.dump(data, output_file, ensure_ascii=False, indent=2)
            output_file.write("\n")
        os.replace(temporary_path, path)
    except OSError:
        if temporary_path.exists():
            temporary_path.unlink()
        raise


def configured_worker_scope():
    prefix = os.environ.get(WORKER_SCOPE_PREFIX_ENV)
    count_text = os.environ.get(WORKER_SCOPE_COUNT_ENV)
    if prefix is None and count_text is None:
        return None
    if not prefix or not WORKER_PATTERN.fullmatch(prefix):
        raise ValueError(f"{WORKER_SCOPE_PREFIX_ENV} contiene un prefix inválido")
    try:
        count = int(count_text)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{WORKER_SCOPE_COUNT_ENV} debe ser un entero") from error
    if not 2 <= count <= 8:
        raise ValueError(f"{WORKER_SCOPE_COUNT_ENV} debe estar entre 2 y 8")
    return prefix, {f"{prefix}-{index}" for index in range(1, count + 1)}


def validate_worker_scope(worker):
    scope = configured_worker_scope()
    if scope is None:
        return
    prefix, allowed_workers = scope
    if worker not in allowed_workers:
        allowed = ", ".join(sorted(allowed_workers))
        raise ValueError(
            f"worker fuera del ámbito de {prefix}: {worker!r}; use uno de {allowed}"
        )


def validate_release_prefix_scope(prefix):
    scope = configured_worker_scope()
    if scope is not None and prefix != scope[0]:
        raise ValueError(
            f"prefix fuera del ámbito de la granja: {prefix!r}; use {scope[0]}"
        )


@contextmanager
def catalog_lock(catalog_path):
    lock_path = catalog_path.with_name(f".{catalog_path.name}.agent.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as lock_file:
        try:
            import fcntl
        except ImportError as error:
            raise RuntimeError(
                "la coordinación multiagente requiere un lock de archivo compatible"
            ) from error
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def lease_registry_path(catalog_path):
    return catalog_path.with_name(f".{catalog_path.name}.agent-leases.json")


def load_lease_registry(path, catalog_path):
    if not path.exists():
        return {
            "schema_version": LEASE_SCHEMA_VERSION,
            "catalog": str(catalog_path.resolve()),
            "leases": [],
        }
    registry = json.loads(path.read_text(encoding="utf-8"))
    if registry.get("schema_version") != LEASE_SCHEMA_VERSION:
        raise ValueError("versión inválida del registro de reservas")
    if registry.get("catalog") != str(catalog_path.resolve()):
        raise ValueError("el registro de reservas pertenece a otro catálogo")
    if not isinstance(registry.get("leases"), list):
        raise ValueError("el registro de reservas no contiene una lista leases")
    return registry


def prune_leases(registry, now=None):
    now = time.time() if now is None else now
    active = []
    for lease in registry.get("leases", []):
        if lease.get("expires_at", 0) > now:
            active.append(lease)
    changed = len(active) != len(registry.get("leases", []))
    registry["leases"] = active
    return changed


def effective_entry_list(data):
    effective = {}
    for index, entry in enumerate(data.get("entries", [])):
        entry_id = entry.get("id")
        if (
            not isinstance(entry_id, str)
            or not entry_id.strip()
            or not entry.get("duplicate_meta", {}).get("selected", True)
            or "orphan_meta" in entry
        ):
            continue
        effective[entry_id] = (index, entry)
    return [entry for _, entry in sorted(effective.values(), key=lambda item: item[0])]


def needs_translation(entry, mode):
    if entry.get("status") == "pending":
        return True
    return (
        mode == "incomplete"
        and entry.get("status") == "translated"
        and entry.get("translation_meta", {}).get("origin") == "source_placeholder"
        and entry.get("translation") == entry.get("source")
    )


def eligible_entries(data, count, mode="pending", reserved_ids=None):
    reserved_ids = reserved_ids or set()
    selected = []
    for entry in reversed(effective_entry_list(data)):
        entry_id = entry.get("id")
        if (
            entry_id in reserved_ids
            or not needs_translation(entry, mode)
            or not isinstance(entry.get("source"), str)
            or not entry["source"]
            or entry_id.startswith(SYSTEM_ID_PREFIXES)
        ):
            continue
        selected.append(entry)
        if len(selected) == count:
            break
    return list(reversed(selected))


def batch_manifest_hash(batch):
    immutable = {
        key: value
        for key, value in batch.items()
        if key not in {"manifest_hash", "lease_expires_at", "entries"}
    }
    immutable["entries"] = [
        {key: value for key, value in item.items() if key != "translation"}
        for item in batch.get("entries", [])
    ]
    return value_hash(immutable)


def default_batch_path(worker, batch_id):
    return ROOT / ".agent" / "batches" / f"{worker}-{batch_id[:12]}.json"


def default_response_path(worker, batch_id):
    return ROOT / ".agent" / "responses" / f"{worker}-{batch_id[:12]}.json"


def response_template(batch):
    return {
        "schema_version": RESPONSE_SCHEMA_VERSION,
        "batch_id": batch["batch_id"],
        "worker": batch["worker"],
        "translations": [
            {"id": entry["id"], "translation": ""}
            for entry in batch["entries"]
        ],
    }


def validate_response(response, batch):
    if set(response) != {"schema_version", "batch_id", "worker", "translations"}:
        raise ValueError("la respuesta contiene campos no permitidos")
    if response.get("schema_version") != RESPONSE_SCHEMA_VERSION:
        raise ValueError(f"response schema_version debe ser {RESPONSE_SCHEMA_VERSION}")
    if response.get("batch_id") != batch["batch_id"]:
        raise ValueError("la respuesta pertenece a otro batch_id")
    if response.get("worker") != batch["worker"]:
        raise ValueError("la respuesta pertenece a otro worker")
    translations = response.get("translations")
    if not isinstance(translations, list):
        raise ValueError("la respuesta no contiene una lista translations")
    if any(
        not isinstance(item, dict) or set(item) != {"id", "translation"}
        for item in translations
    ):
        raise ValueError("cada respuesta debe contener solo id y translation")
    expected_ids = [entry["id"] for entry in batch["entries"]]
    response_ids = [item.get("id") for item in translations]
    if response_ids != expected_ids:
        raise ValueError("los IDs de la respuesta no coinciden con el lote")
    return {item["id"]: item.get("translation") for item in translations}


def lease_expiration_text(expires_at):
    return datetime.fromtimestamp(expires_at, timezone.utc).isoformat()


def export_batch(project_path, output_path, count, mode, worker, lease_seconds):
    project = load_project(project_path)
    catalog_path = resolve_project_path(project, "catalog").resolve(strict=True)
    rules = json.loads(DEFAULT_RULES.read_text(encoding="utf-8"))
    registry_path = lease_registry_path(catalog_path)
    with catalog_lock(catalog_path):
        data = json.loads(catalog_path.read_text(encoding="utf-8"))
        registry = load_lease_registry(registry_path, catalog_path)
        prune_leases(registry)
        for lease in registry["leases"]:
            if lease.get("worker") == worker:
                active_path = Path(lease["batch_path"])
                response_path = Path(lease.get("response_path", ""))
                if not active_path.is_file() or not response_path.is_file():
                    raise ValueError(
                        f"el worker {worker} tiene una reserva incompleta; "
                        f"libérela por batch_id {lease['batch_id']}"
                    )
                save_json(registry_path, registry)
                print(f"Lote activo reutilizado para {worker}: {active_path}")
                print(f"BATCH_FILE {active_path}")
                print(f"RESPONSE_FILE {response_path}")
                print(f"BATCH_ID {lease['batch_id']}")
                return 0

        reserved_ids = {
            entry_id
            for lease in registry["leases"]
            for entry_id in lease.get("entry_ids", [])
        }
        entries = eligible_entries(data, count, mode, reserved_ids)
        if not entries:
            save_json(registry_path, registry)
            raise ValueError(f"no hay entradas disponibles para exportar en modo {mode}")

        batch_id = uuid.uuid4().hex
        expires_at = time.time() + lease_seconds
        explicit_output = output_path is not None
        output_path = output_path or default_batch_path(worker, batch_id)
        response_path = (
            output_path.with_name(f"{output_path.stem}.response.json")
            if explicit_output
            else default_response_path(worker, batch_id)
        )
        if output_path.exists():
            raise ValueError(f"el archivo de lote ya existe: {output_path}")
        if response_path.exists():
            raise ValueError(f"el archivo de respuesta ya existe: {response_path}")
        batch_entries = [
            {
                "id": entry["id"],
                "source": entry["source"],
                "source_hash": source_hash(entry["id"], entry["source"]),
                "entry_hash": entry_hash(entry),
                "protected_tokens": protected_tokens(entry["source"], rules),
            }
            for entry in entries
        ]
        batch = {
            "schema_version": SCHEMA_VERSION,
            "batch_id": batch_id,
            "worker": worker,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "lease_expires_at": lease_expiration_text(expires_at),
            "project": project["name"],
            "language": project["language"],
            "catalog": project["catalog"],
            "mode": mode,
            "rules_hash": value_hash(rules),
            "response_file": str(response_path.resolve()),
            "instructions": (
                "This batch is read-only. Fill only translation values in RESPONSE_FILE."
            ),
            "entries": batch_entries,
        }
        batch["manifest_hash"] = batch_manifest_hash(batch)
        save_json(output_path, batch)
        save_json(response_path, response_template(batch))
        registry["leases"].append({
            "batch_id": batch_id,
            "worker": worker,
            "mode": mode,
            "batch_path": str(output_path.resolve()),
            "response_path": str(response_path.resolve()),
            "entry_ids": [entry["id"] for entry in entries],
            "entry_hashes": [entry_hash(entry) for entry in entries],
            "created_at": batch["created_at"],
            "expires_at": expires_at,
        })
        save_json(registry_path, registry)

    print(f"Lote para agente: {output_path}")
    print(f"Entradas exportadas: {len(entries)}")
    print(f"Reserva válida hasta: {batch['lease_expires_at']}")
    print(f"BATCH_FILE {output_path.resolve()}")
    print(f"RESPONSE_FILE {response_path.resolve()}")
    print(f"BATCH_ID {batch_id}")
    print(
        "Después de completar translation, aplicar con: "
        f"python3 tools/localization/agent_batch.py apply --project {project_path} "
        f"--input {output_path} --response {response_path}"
    )
    return 0


def effective_entries(data):
    return {entry["id"]: entry for entry in effective_entry_list(data)}


def validate_batch(batch):
    if batch.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"schema_version debe ser {SCHEMA_VERSION}")
    entries = batch.get("entries")
    if not isinstance(entries, list) or not entries:
        raise ValueError("el lote no contiene entradas")
    ids = [entry.get("id") for entry in entries if isinstance(entry, dict)]
    if len(ids) != len(entries) or len(ids) != len(set(ids)):
        raise ValueError("cada entrada debe tener un id único")
    if not isinstance(batch.get("batch_id"), str) or not batch["batch_id"]:
        raise ValueError("el lote no contiene batch_id")
    if batch.get("manifest_hash") != batch_manifest_hash(batch):
        raise ValueError("el manifiesto inmutable del lote fue modificado")
    return entries


def apply_batch(project_path, input_path, response_path, actor, model):
    project = load_project(project_path)
    catalog_path = resolve_project_path(project, "catalog").resolve(strict=True)
    rules = json.loads(DEFAULT_RULES.read_text(encoding="utf-8"))

    with catalog_lock(catalog_path):
        batch_bytes = input_path.read_bytes()
        batch = json.loads(batch_bytes.decode("utf-8"))
        batch_entries = validate_batch(batch)
        configured_response_path = Path(batch.get("response_file", ""))
        response_path = response_path or configured_response_path
        if response_path.resolve() != configured_response_path.resolve():
            raise ValueError("la ruta de respuesta no coincide con el lote")
        response_bytes = response_path.read_bytes()
        response = json.loads(response_bytes.decode("utf-8"))
        translations = validate_response(response, batch)
        mode = batch.get("mode", "pending")
        if mode not in {"pending", "incomplete"}:
            raise ValueError(f"modo de lote inválido: {mode!r}")
        if batch.get("project") != project["name"] or batch.get("catalog") != project["catalog"]:
            raise ValueError("el lote pertenece a otro proyecto o catálogo")
        if batch.get("language") != project["language"]:
            raise ValueError("el lote pertenece a otro idioma de destino")
        if batch.get("rules_hash") != value_hash(rules):
            raise ValueError("las reglas de tokens cambiaron; exporte otro lote")

        data = json.loads(catalog_path.read_text(encoding="utf-8"))
        registry_path = lease_registry_path(catalog_path)
        registry = load_lease_registry(registry_path, catalog_path)
        prune_leases(registry)
        lease = None
        lease = next(
            (
                item for item in registry["leases"]
                if item.get("batch_id") == batch["batch_id"]
            ),
            None,
        )
        if lease is None:
            save_json(registry_path, registry)
            raise ValueError("la reserva del lote venció o ya fue liberada")
        if lease.get("worker") != batch.get("worker"):
            raise ValueError("el worker del lote no coincide con la reserva")
        if Path(lease.get("batch_path", "")).resolve() != input_path.resolve():
            raise ValueError("la ruta del lote no coincide con la reserva")
        if Path(lease.get("response_path", "")).resolve() != response_path.resolve():
            raise ValueError("la ruta de respuesta no coincide con la reserva")
        if lease.get("entry_ids") != [item["id"] for item in batch_entries]:
            raise ValueError("las entradas del lote no coinciden con la reserva")
        if lease.get("entry_hashes") != [item.get("entry_hash") for item in batch_entries]:
            raise ValueError("los hashes del lote no coinciden con la reserva")

        current_entries = effective_entries(data)
        prepared = []
        for item in batch_entries:
            entry_id = item["id"]
            entry = current_entries.get(entry_id)
            if entry is None:
                raise ValueError(f"{entry_id}: la entrada ya no existe o no es efectiva")
            source = entry.get("source")
            if item.get("source") != source or item.get("source_hash") != source_hash(entry_id, source):
                raise ValueError(f"{entry_id}: el texto fuente cambió; exporte otro lote")
            if item.get("entry_hash") != entry_hash(entry):
                raise ValueError(f"{entry_id}: la entrada cambió; exporte otro lote")
            expected_tokens = protected_tokens(source, rules)
            if item.get("protected_tokens") != expected_tokens:
                raise ValueError(f"{entry_id}: protected_tokens fue modificado")
            if not needs_translation(entry, mode):
                raise ValueError(f"{entry_id}: la entrada ya no es elegible en modo {mode}")
            translation = translations.get(entry_id)
            if not isinstance(translation, str) or not translation.strip():
                raise ValueError(f"{entry_id}: translation está vacía")
            if not protected_tokens_match(source, translation, rules):
                actual = protected_tokens(translation, rules)
                raise ValueError(
                    f"{entry_id}: tokens inválidos; esperado {expected_tokens}, recibido {actual}"
                )
            letter = hotkey_letter(source) or hotkey_letter(translation)
            translation = normalize_hotkey_text(translation, letter) if letter else translation
            if not protected_tokens_match(source, translation, rules):
                raise ValueError(f"{entry_id}: la normalización de hotkeys produjo tokens inválidos")
            prepared.append((entry, translation))

        today = datetime.now().strftime("%Y-%m-%d")
        for entry, translation in prepared:
            previous = entry.get("translation", "")
            entry["translation"] = translation
            entry["status"] = "translated"
            flags = entry.setdefault("flags", [])
            if "needs_review" not in flags:
                flags.append("needs_review")
            entry.setdefault("translation_meta", {}).update({
                "origin": "agent",
                "model": model,
                "date": today,
                "confidence": 0.0,
            })
            entry.setdefault("history", []).append({
                "date": today,
                "action": "translated",
                "from": previous,
                "to": translation,
                "by": actor,
            })
        if input_path.read_bytes() != batch_bytes:
            raise ValueError("el archivo de lote cambió durante la aplicación")
        if response_path.read_bytes() != response_bytes:
            raise ValueError("el archivo de respuesta cambió durante la aplicación")
        save_json(catalog_path, data)
        registry["leases"] = [
            item for item in registry["leases"]
            if item.get("batch_id") != batch["batch_id"]
        ]
        save_json(registry_path, registry)

    print(f"Catálogo actualizado: {catalog_path}")
    print(f"Entradas aplicadas: {len(prepared)}")
    return 0


def status(project_path, mode, as_json):
    project = load_project(project_path)
    catalog_path = resolve_project_path(project, "catalog").resolve(strict=True)
    registry_path = lease_registry_path(catalog_path)
    with catalog_lock(catalog_path):
        data = json.loads(catalog_path.read_text(encoding="utf-8"))
        registry = load_lease_registry(registry_path, catalog_path)
        prune_leases(registry)
        save_json(registry_path, registry)

    eligible = eligible_entries(data, len(data.get("entries", [])), mode)
    eligible_ids = {entry["id"] for entry in eligible}
    reserved_ids = {
        entry_id
        for lease in registry["leases"]
        for entry_id in lease.get("entry_ids", [])
        if entry_id in eligible_ids
    }
    result = {
        "project": project["name"],
        "language": project["language"],
        "mode": mode,
        "eligible": len(eligible_ids),
        "reserved": len(reserved_ids),
        "available": len(eligible_ids - reserved_ids),
        "active_batches": [
            {
                "batch_id": lease["batch_id"],
                "worker": lease["worker"],
                "entries": len(lease.get("entry_ids", [])),
                "expires_at": lease_expiration_text(lease["expires_at"]),
                "batch_path": lease["batch_path"],
                "response_path": lease.get("response_path"),
            }
            for lease in registry["leases"]
        ],
    }
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Proyecto: {result['project']} ({result['language']})")
        print(f"Entradas incompletas: {result['eligible']}")
        print(f"Entradas reservadas: {result['reserved']}")
        print(f"Entradas disponibles: {result['available']}")
        print(f"Lotes activos: {len(result['active_batches'])}")
        for lease in result["active_batches"]:
            print(
                f"  {lease['worker']}: {lease['entries']} entradas, "
                f"vence {lease['expires_at']} ({lease['batch_id']})"
            )
    return 0


def update_lease(project_path, input_path, lease_seconds=None, release=False):
    project = load_project(project_path)
    catalog_path = resolve_project_path(project, "catalog").resolve(strict=True)

    registry_path = lease_registry_path(catalog_path)
    with catalog_lock(catalog_path):
        batch = json.loads(input_path.read_text(encoding="utf-8"))
        validate_batch(batch)
        if batch.get("project") != project["name"] or batch.get("catalog") != project["catalog"]:
            raise ValueError("el lote pertenece a otro proyecto o catálogo")
        registry = load_lease_registry(registry_path, catalog_path)
        prune_leases(registry)
        lease = next(
            (
                item for item in registry["leases"]
                if item.get("batch_id") == batch["batch_id"]
            ),
            None,
        )
        if lease is None:
            save_json(registry_path, registry)
            raise ValueError("la reserva del lote venció o ya fue liberada")
        if lease.get("worker") != batch.get("worker"):
            raise ValueError("el worker del lote no coincide con la reserva")
        if Path(lease.get("batch_path", "")).resolve() != input_path.resolve():
            raise ValueError("la ruta del lote no coincide con la reserva")
        if release:
            registry["leases"] = [
                item for item in registry["leases"]
                if item.get("batch_id") != batch["batch_id"]
            ]
            save_json(registry_path, registry)
            print(f"Reserva liberada: {batch['batch_id']}")
            return 0

        expires_at = max(lease["expires_at"], time.time() + lease_seconds)
        lease["expires_at"] = expires_at
        save_json(registry_path, registry)
    print(f"Reserva renovada hasta: {lease_expiration_text(expires_at)}")
    return 0


def reset_response(project_path, input_path):
    project = load_project(project_path)
    catalog_path = resolve_project_path(project, "catalog").resolve(strict=True)
    registry_path = lease_registry_path(catalog_path)
    with catalog_lock(catalog_path):
        batch = json.loads(input_path.read_text(encoding="utf-8"))
        validate_batch(batch)
        registry = load_lease_registry(registry_path, catalog_path)
        prune_leases(registry)
        lease = next(
            (
                item for item in registry["leases"]
                if item.get("batch_id") == batch["batch_id"]
                and item.get("worker") == batch["worker"]
            ),
            None,
        )
        if lease is None:
            raise ValueError("la reserva del lote venció o ya fue liberada")
        if Path(lease.get("batch_path", "")).resolve() != input_path.resolve():
            raise ValueError("la ruta del lote no coincide con la reserva")
        response_path = Path(lease["response_path"])
        save_json(response_path, response_template(batch))
    print(f"Respuesta reiniciada: {response_path}")
    print(f"RESPONSE_FILE {response_path}")
    return 0


def release_lease(project_path, batch_id, worker):
    project = load_project(project_path)
    catalog_path = resolve_project_path(project, "catalog").resolve(strict=True)
    registry_path = lease_registry_path(catalog_path)
    with catalog_lock(catalog_path):
        registry = load_lease_registry(registry_path, catalog_path)
        prune_leases(registry)
        lease = next(
            (
                item for item in registry["leases"]
                if item.get("batch_id") == batch_id and item.get("worker") == worker
            ),
            None,
        )
        if lease is None:
            save_json(registry_path, registry)
            raise ValueError("no existe una reserva activa para ese batch_id y worker")
        registry["leases"] = [
            item for item in registry["leases"]
            if item.get("batch_id") != batch_id
        ]
        save_json(registry_path, registry)
    print(f"Reserva liberada: {batch_id}")
    return 0


def release_prefix(project_path, prefix):
    project = load_project(project_path)
    catalog_path = resolve_project_path(project, "catalog").resolve(strict=True)
    registry_path = lease_registry_path(catalog_path)

    with catalog_lock(catalog_path):
        registry = load_lease_registry(registry_path, catalog_path)
        prune_leases(registry)
        released = [
            lease
            for lease in registry["leases"]
            if lease.get("worker") == prefix
            or lease.get("worker", "").startswith(f"{prefix}-")
        ]
        registry["leases"] = [
            lease for lease in registry["leases"] if lease not in released
        ]
        save_json(registry_path, registry)

    released_entries = sum(len(lease.get("entry_ids", [])) for lease in released)
    print(f"Reservas liberadas para {prefix}: {len(released)}")
    print(f"Entradas devueltas: {released_entries}")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Exchange small, validated translation batches with an external agent."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    export_parser = subparsers.add_parser(
        "export", help="Reserve and export pending entries to a small JSON batch"
    )
    export_parser.add_argument("--project", required=True, type=Path)
    export_parser.add_argument(
        "--output",
        type=Path,
        help="Explicit batch path; defaults to a unique path under .agent/batches",
    )
    export_parser.add_argument("--count", type=int, default=20)
    export_parser.add_argument("--worker", default="single-agent")
    export_parser.add_argument(
        "--lease-seconds",
        type=int,
        default=DEFAULT_LEASE_SECONDS,
        help="Reservation lifetime before entries return to the queue",
    )
    export_parser.add_argument(
        "--mode",
        choices=("pending", "incomplete"),
        default="incomplete",
        help="incomplete also includes exact source placeholders",
    )
    apply_parser = subparsers.add_parser("apply", help="Validate and apply a completed JSON batch")
    apply_parser.add_argument("--project", required=True, type=Path)
    apply_parser.add_argument("--input", required=True, type=Path)
    apply_parser.add_argument(
        "--response",
        type=Path,
        help="Completed response JSON; defaults to response_file recorded in the batch",
    )
    apply_parser.add_argument("--actor", default="translation-agent")
    apply_parser.add_argument("--model", default="external-llm")

    status_parser = subparsers.add_parser(
        "status", help="Show aggregate queue and reservation status"
    )
    status_parser.add_argument("--project", required=True, type=Path)
    status_parser.add_argument(
        "--mode", choices=("pending", "incomplete"), default="incomplete"
    )
    status_parser.add_argument("--json", action="store_true", dest="as_json")

    renew_parser = subparsers.add_parser("renew", help="Extend an active batch lease")
    renew_parser.add_argument("--project", required=True, type=Path)
    renew_parser.add_argument("--input", required=True, type=Path)
    renew_parser.add_argument(
        "--lease-seconds", type=int, default=DEFAULT_LEASE_SECONDS
    )

    release_parser = subparsers.add_parser(
        "release", help="Release a batch lease without applying translations"
    )
    release_parser.add_argument("--project", required=True, type=Path)
    release_group = release_parser.add_mutually_exclusive_group(required=True)
    release_group.add_argument("--input", type=Path)
    release_group.add_argument("--batch-id")
    release_parser.add_argument("--worker")

    release_prefix_parser = subparsers.add_parser(
        "release-prefix", help="Release every active lease owned by a worker prefix"
    )
    release_prefix_parser.add_argument("--project", required=True, type=Path)
    release_prefix_parser.add_argument("--prefix", required=True)

    reset_parser = subparsers.add_parser(
        "reset-response", help="Recreate an empty response file for an active batch"
    )
    reset_parser.add_argument("--project", required=True, type=Path)
    reset_parser.add_argument("--input", required=True, type=Path)

    args = parser.parse_args()
    if args.command == "export" and not 1 <= args.count <= 100:
        parser.error("--count debe estar entre 1 y 100")
    if args.command == "export" and not WORKER_PATTERN.fullmatch(args.worker):
        parser.error("--worker debe usar 1-64 caracteres: letras, números, punto, guion o guion bajo")
    if args.command in {"export", "renew"} and not 60 <= args.lease_seconds <= 604800:
        parser.error("--lease-seconds debe estar entre 60 y 604800")
    if args.command == "release" and args.batch_id and not args.worker:
        parser.error("--worker es obligatorio al liberar por --batch-id")
    if args.command == "release-prefix" and not WORKER_PATTERN.fullmatch(args.prefix):
        parser.error("--prefix debe usar 1-64 caracteres: letras, números, punto, guion o guion bajo")
    try:
        if args.command == "export":
            validate_worker_scope(args.worker)
        elif args.command == "apply":
            validate_worker_scope(args.actor)
        elif args.command == "release" and args.worker:
            validate_worker_scope(args.worker)
        elif args.command == "release-prefix":
            validate_release_prefix_scope(args.prefix)
    except ValueError as error:
        parser.error(str(error))
    try:
        if args.command == "export":
            return export_batch(
                args.project,
                args.output,
                args.count,
                args.mode,
                args.worker,
                args.lease_seconds,
            )
        if args.command == "apply":
            return apply_batch(
                args.project, args.input, args.response, args.actor, args.model
            )
        if args.command == "status":
            return status(args.project, args.mode, args.as_json)
        if args.command == "renew":
            return update_lease(args.project, args.input, args.lease_seconds)
        if args.command == "reset-response":
            return reset_response(args.project, args.input)
        if args.command == "release-prefix":
            return release_prefix(args.project, args.prefix)
        if args.input:
            return update_lease(args.project, args.input, release=True)
        return release_lease(args.project, args.batch_id, args.worker)
    except (OSError, RuntimeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
