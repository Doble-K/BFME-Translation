#!/usr/bin/env python3

import argparse
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from agent_batch import (
    WORKER_SCOPE_COUNT_ENV,
    WORKER_SCOPE_PREFIX_ENV,
    release_catalog_workers,
    save_json,
)
from project import (
    PROJECT_SCOPE_PATH_ENV,
    PROJECT_SCOPE_REVISION_ENV,
    canonical_project_path,
    load_project,
    project_revision,
    resolve_project_path,
)
from watch_progress import catalog_progress_snapshot


ROOT = Path(__file__).resolve().parents[2]
STATE_SCHEMA_VERSION = 3
CONTROL_SCHEMA_VERSION = 1
SUPERVISOR_CHILD_ENV = "SAGE_LOCALIZATION_FARM_SUPERVISOR_CHILD"
COORDINATOR_TOKEN_ENV = "SAGE_LOCALIZATION_FARM_COORDINATOR_TOKEN"
PREFIX_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,55}$")


def resolve_root_path(value):
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def profile_runtime_root(config_path):
    config_path = Path(config_path).resolve()
    try:
        config_path.relative_to(ROOT)
    except ValueError:
        return config_path.parent / ".agent"
    return ROOT / ".agent"


def runtime_anchor_path(config_path):
    config_path = Path(config_path).resolve()
    digest = hashlib.md5(
        str(config_path).encode("utf-8"), usedforsecurity=False
    ).hexdigest()
    return profile_runtime_root(config_path) / "farm-runtime" / f"{digest}.json"


def path_is_within(path, directory):
    try:
        Path(path).resolve().relative_to(Path(directory).resolve())
    except ValueError:
        return False
    return True


def validate_runtime_paths(config_path, project_path, catalog_path, paths):
    allowed_roots = {ROOT / ".agent", profile_runtime_root(config_path)}
    for label, path in paths.items():
        if not any(path_is_within(path, root) for root in allowed_roots):
            raise ValueError(f"{label} debe estar dentro de un directorio .agent")
        if label in {"state_file", "control_file"} and any(
            path_is_within(path, root / "farm-runtime") for root in allowed_roots
        ):
            raise ValueError(f"{label} no puede usar el directorio farm-runtime")
    files = {
        "perfil": config_path,
        "proyecto": project_path,
        "catálogo": catalog_path,
        "estado": paths["state_file"],
        "control": paths["control_file"],
        "acuse": paths["state_file"].with_name(
            f"{paths['state_file'].stem}.ack.json"
        ),
    }
    resolved = {label: Path(path).resolve() for label, path in files.items()}
    if len(set(resolved.values())) != len(resolved):
        raise ValueError(
            "las rutas de perfil, proyecto, catálogo y runtime deben ser distintas"
        )


def load_runtime_anchor(path, config_path):
    if not path.exists():
        return None
    anchor = json.loads(path.read_text(encoding="utf-8"))
    if anchor.get("schema_version") != 1:
        raise ValueError("versión inválida del anclaje runtime de la granja")
    if Path(anchor.get("config", "")).resolve() != config_path:
        raise ValueError("el anclaje runtime pertenece a otro perfil")
    if not all(
        isinstance(anchor.get(field), str) and anchor[field]
        for field in ("state_file", "control_file")
    ):
        raise ValueError("el anclaje runtime no contiene rutas válidas")
    return anchor


def load_farm_config(path):
    config_path = Path(path).resolve(strict=True)
    data = json.loads(config_path.read_text(encoding="utf-8"))
    coordinators = data.get("coordinators")
    workers = data.get("workers", 4)
    count = data.get("count", 25)
    max_restarts = data.get("max_restarts", 1)
    poll_seconds = data.get("poll_seconds", 5)

    if not isinstance(coordinators, list) or not coordinators:
        raise ValueError("coordinators debe ser una lista no vacía")
    if len(coordinators) > 16:
        raise ValueError("coordinators admite como máximo 16 entradas")
    if not isinstance(workers, int) or not 2 <= workers <= 8:
        raise ValueError("workers debe estar entre 2 y 8")
    if not isinstance(count, int) or not 1 <= count <= 100:
        raise ValueError("count debe estar entre 1 y 100")
    if not isinstance(max_restarts, int) or not 0 <= max_restarts <= 10:
        raise ValueError("max_restarts debe estar entre 0 y 10")
    if (
        not isinstance(poll_seconds, (int, float))
        or not 1 <= poll_seconds <= 10
    ):
        raise ValueError("poll_seconds debe estar entre 1 y 10 segundos")

    normalized = []
    prefixes = set()
    for item in coordinators:
        if not isinstance(item, dict):
            raise ValueError("cada coordinador debe ser un objeto")
        prefix = item.get("prefix")
        model = item.get("model")
        if not isinstance(prefix, str) or not PREFIX_PATTERN.fullmatch(prefix):
            raise ValueError(f"prefix inválido: {prefix!r}")
        if prefix in prefixes:
            raise ValueError(f"prefix duplicado: {prefix}")
        if not isinstance(model, str) or "/" not in model:
            raise ValueError(f"model debe usar provider/model para {prefix}")
        prefixes.add(prefix)
        normalized.append({"prefix": prefix, "model": model})

    for prefix in prefixes:
        if any(
            other != prefix
            and (
                prefix.startswith(f"{other}-")
                or other.startswith(f"{prefix}-")
            )
            for other in prefixes
        ):
            raise ValueError("los prefixes de coordinadores no pueden solaparse")

    project_path = canonical_project_path(
        resolve_root_path(data.get("project", "config/project.json"))
    )
    project = load_project(project_path)
    catalog_path = resolve_project_path(project, "catalog").resolve(strict=True)
    configured_state_file = resolve_root_path(
        data.get("state_file", ".agent/opencode-farm-state.json")
    )
    configured_control_file = resolve_root_path(
        data.get(
            "control_file",
            str(configured_state_file.with_name(
                f"{configured_state_file.stem}.control.json"
            )),
        )
    )
    anchor_file = runtime_anchor_path(config_path)
    anchor = load_runtime_anchor(anchor_file, config_path)
    state_file = (
        Path(anchor["state_file"]).resolve()
        if anchor
        else configured_state_file
    )
    control_file = (
        Path(anchor["control_file"]).resolve()
        if anchor
        else configured_control_file
    )
    log_directory = resolve_root_path(
        data.get("log_directory", ".agent/logs/opencode-farm")
    )
    validate_runtime_paths(config_path, project_path, catalog_path, {
        "state_file": state_file,
        "control_file": control_file,
        "log_directory": log_directory,
    })
    return {
        "runtime_fallback": False,
        "config_path": config_path,
        "project": project_path,
        "project_revision": project_revision(project_path),
        "project_name": project["name"],
        "language": project["language"],
        "catalog": catalog_path,
        "workers": workers,
        "count": count,
        "max_restarts": max_restarts,
        "poll_seconds": float(poll_seconds),
        "configured_state_file": configured_state_file,
        "configured_control_file": configured_control_file,
        "state_file": state_file,
        "control_file": control_file,
        "ack_file": state_file.with_name(f"{state_file.stem}.ack.json"),
        "runtime_anchor_file": anchor_file,
        "lifecycle_lock_file": anchor_file.with_name(f".{anchor_file.name}.lock"),
        "log_directory": log_directory,
        "coordinators": normalized,
    }


def load_farm_runtime(path):
    config_path = Path(path).expanduser().resolve()
    anchor_file = runtime_anchor_path(config_path)
    anchor = load_runtime_anchor(anchor_file, config_path)
    if anchor is None or not isinstance(anchor.get("runtime"), dict):
        raise ValueError("no existe un estado runtime recuperable para el perfil")
    runtime = anchor["runtime"]
    required = {
        "project",
        "project_revision",
        "project_name",
        "language",
        "catalog",
        "workers",
        "count",
        "max_restarts",
        "poll_seconds",
        "log_directory",
        "coordinators",
    }
    if not required.issubset(runtime):
        raise ValueError("el anclaje runtime está incompleto")
    state_file = Path(anchor["state_file"]).resolve()
    control_file = Path(anchor["control_file"]).resolve()
    project_path = Path(runtime["project"]).resolve()
    catalog_path = Path(runtime["catalog"]).resolve()
    log_directory = Path(runtime["log_directory"]).resolve()
    validate_runtime_paths(config_path, project_path, catalog_path, {
        "state_file": state_file,
        "control_file": control_file,
        "log_directory": log_directory,
    })
    return {
        "runtime_fallback": True,
        "config_path": config_path,
        "project": project_path,
        "project_revision": runtime["project_revision"],
        "project_name": runtime["project_name"],
        "language": runtime["language"],
        "catalog": catalog_path,
        "workers": runtime["workers"],
        "count": runtime["count"],
        "max_restarts": runtime["max_restarts"],
        "poll_seconds": runtime["poll_seconds"],
        "configured_state_file": state_file,
        "configured_control_file": control_file,
        "state_file": state_file,
        "control_file": control_file,
        "ack_file": state_file.with_name(f"{state_file.stem}.ack.json"),
        "runtime_anchor_file": anchor_file,
        "lifecycle_lock_file": anchor_file.with_name(f".{anchor_file.name}.lock"),
        "log_directory": log_directory,
        "coordinators": runtime["coordinators"],
    }


def load_farm_config_with_runtime_fallback(path):
    try:
        return load_farm_config(path)
    except (OSError, ValueError, json.JSONDecodeError):
        return load_farm_runtime(path)


def build_opencode_command(coordinator, project_path, workers, count):
    arguments = json.dumps({
        "project": str(canonical_project_path(project_path)),
        "prefix": coordinator["prefix"],
        "workers": workers,
        "count": count,
    }, ensure_ascii=True, separators=(",", ":"))
    return [
        "opencode",
        "run",
        "--agent",
        "translation-coordinator",
        "--model",
        coordinator["model"],
        "--title",
        coordinator["prefix"],
        "--command",
        "translate-parallel",
        arguments,
    ]


def process_is_alive(pid):
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def proc_stat(pid):
    try:
        value = (Path("/proc") / str(pid) / "stat").read_text(encoding="utf-8")
        fields = value.rsplit(")", 1)[1].strip().split()
        return {
            "process_group": int(fields[2]),
            "start_time": fields[19],
        }
    except (IndexError, OSError, ValueError):
        return None


def process_identity(pid):
    stat = proc_stat(pid)
    if stat is None:
        return None
    try:
        boot_id = Path("/proc/sys/kernel/random/boot_id").read_text(
            encoding="ascii"
        ).strip()
    except OSError:
        return None
    if not boot_id:
        return None
    return f"{boot_id}:{stat['start_time']}"


def process_command(pid):
    try:
        value = (Path("/proc") / str(pid) / "cmdline").read_bytes()
    except OSError:
        return None
    return [
        item.decode("utf-8", errors="replace")
        for item in value.split(b"\0")
        if item
    ]


def legacy_supervisor_matches(state):
    command = process_command(state.get("supervisor_pid"))
    if not command:
        return False
    expected_script = str(Path(__file__).resolve())
    expected_config = str(Path(state.get("config", "")).resolve())
    return expected_script in command and expected_config in command


def supervisor_is_alive(state):
    if not state or not process_is_alive(state.get("supervisor_pid")):
        return False
    expected_identity = state.get("supervisor_identity")
    if state.get("schema_version") == STATE_SCHEMA_VERSION:
        if not isinstance(expected_identity, str) or not expected_identity:
            raise RuntimeError("el estado actual no identifica al supervisor")
        current_identity = process_identity(state["supervisor_pid"])
        if current_identity is None:
            raise RuntimeError("no se pudo verificar la identidad del supervisor")
        return current_identity == expected_identity
    if expected_identity:
        return process_identity(state["supervisor_pid"]) == expected_identity
    return legacy_supervisor_matches(state)


def process_group_is_alive(process_group_id):
    if not isinstance(process_group_id, int) or process_group_id <= 0:
        return False
    try:
        os.killpg(process_group_id, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def process_group_has_token(process_group_id, token):
    proc_root = Path("/proc")
    if not proc_root.is_dir():
        return None
    expected = f"{COORDINATOR_TOKEN_ENV}={token}".encode("utf-8")
    member_found = False
    unreadable_member = False
    try:
        entries = list(os.scandir(proc_root))
    except OSError:
        return None
    for entry in entries:
        if not entry.name.isdigit():
            continue
        stat = proc_stat(int(entry.name))
        if stat is None or stat["process_group"] != process_group_id:
            continue
        member_found = True
        try:
            environment = (Path(entry.path) / "environ").read_bytes().split(b"\0")
        except OSError:
            unreadable_member = True
            continue
        if expected in environment:
            return True
    if unreadable_member:
        return None
    return False if member_found else False


def owned_process_group_is_alive(process_group_id, token):
    if not process_group_is_alive(process_group_id):
        return False
    ownership = process_group_has_token(process_group_id, token)
    if ownership is not True:
        raise RuntimeError(
            f"el grupo coordinador {process_group_id} no pudo verificarse"
        )
    return True


def slot_process_group_is_alive(slot):
    process = slot.get("process")
    if process is None:
        return False
    token = slot.get("token")
    if token:
        return owned_process_group_is_alive(process.pid, token)
    return process_group_is_alive(process.pid)


def legacy_coordinator_matches(child):
    command = process_command(child.get("pid"))
    if command is None:
        return None
    prefix = child.get("prefix")
    return bool(command and prefix in command and any(
        Path(argument).name == "opencode" for argument in command
    ))


def wait_for_process_exit(pid, timeout, expected_identity=None):
    deadline = time.monotonic() + timeout
    while process_is_alive(pid):
        if expected_identity is not None:
            current_identity = process_identity(pid)
            if current_identity is None:
                return False
            if current_identity != expected_identity:
                return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.2)
    return True


def load_state(path):
    if not path.exists():
        return None
    state = json.loads(path.read_text(encoding="utf-8"))
    if state.get("schema_version") not in {1, 2, STATE_SCHEMA_VERSION}:
        raise ValueError("versión inválida del estado de la granja")
    state.setdefault("mode", "running")
    state.setdefault("last_control_id", None)
    return state


def validate_state_owner(state, config):
    if Path(state.get("config", "")).resolve() != config["config_path"]:
        raise ValueError("el estado pertenece a otro perfil de granja")


def validate_state_identity(state, config):
    validate_state_owner(state, config)
    if Path(state.get("project", "")).resolve() != config["project"]:
        raise ValueError("el estado pertenece a otro proyecto")
    if state.get("project_revision") != config["project_revision"]:
        raise ValueError("el proyecto cambió desde que se inició la granja")
    if state.get("catalog") and Path(state["catalog"]).resolve() != config["catalog"]:
        raise ValueError("el estado pertenece a otro catálogo")


def state_catalog(state, config):
    catalog = state.get("catalog")
    if catalog:
        return Path(catalog).resolve(strict=True)
    if (
        Path(state.get("project", "")).resolve() == config["project"]
        and state.get("project_revision") == config["project_revision"]
    ):
        return config["catalog"]
    raise ValueError(
        "el estado antiguo no identifica el catálogo y el proyecto cambió"
    )


def state_prefixes(state, config):
    prefixes = []
    for child in state.get("children", []):
        prefix = child.get("prefix")
        if isinstance(prefix, str) and PREFIX_PATTERN.fullmatch(prefix):
            if prefix not in prefixes:
                prefixes.append(prefix)
    if prefixes:
        return prefixes
    if (
        Path(state.get("project", "")).resolve() == config["project"]
        and state.get("project_revision") == config["project_revision"]
    ):
        return [item["prefix"] for item in config["coordinators"]]
    return []


def state_worker_count(state, config):
    workers = state.get("workers")
    if isinstance(workers, int) and 2 <= workers <= 8:
        return workers
    if (
        Path(state.get("project", "")).resolve() == config["project"]
        and state.get("project_revision") == config["project_revision"]
    ):
        return config["workers"]
    raise ValueError("el estado no identifica la cantidad de workers")


def coordinator_worker_names(prefix, workers):
    return {f"{prefix}-{index}" for index in range(1, workers + 1)}


def bind_runtime_paths(config, create=False):
    anchor_path = config.get("runtime_anchor_file")
    if anchor_path is None:
        return
    anchor = load_runtime_anchor(anchor_path, config["config_path"])
    if anchor is None and create:
        state_file = config.get("configured_state_file", config["state_file"])
        control_file = config.get("configured_control_file", config["control_file"])
        anchor = {
            "schema_version": 1,
            "config": str(config["config_path"]),
            "state_file": str(state_file.resolve()),
            "control_file": str(control_file.resolve()),
            "runtime": {
                "project": str(config["project"]),
                "project_revision": config["project_revision"],
                "project_name": config["project_name"],
                "language": config["language"],
                "catalog": str(config["catalog"]),
                "workers": config["workers"],
                "count": config["count"],
                "max_restarts": config["max_restarts"],
                "poll_seconds": config["poll_seconds"],
                "log_directory": str(config["log_directory"]),
                "coordinators": config["coordinators"],
            },
        }
        save_json(anchor_path, anchor)
    if anchor:
        config["state_file"] = Path(anchor["state_file"]).resolve()
        config["control_file"] = Path(anchor["control_file"]).resolve()
        config["ack_file"] = config["state_file"].with_name(
            f"{config['state_file'].stem}.ack.json"
        )


@contextmanager
def exclusive_file_lock(lock_path):
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as lock_file:
        try:
            import fcntl
        except ImportError as error:
            raise RuntimeError(
                "el control de la granja requiere un lock de archivo compatible"
            ) from error
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


@contextmanager
def farm_lifecycle_lock(config):
    profile_lock = config.get(
        "lifecycle_lock_file",
        config["state_file"].with_name(f".{config['state_file'].name}.profile.lock"),
    )
    with exclusive_file_lock(profile_lock):
        bind_runtime_paths(config, create=True)
        state_lock = config["state_file"].with_name(
            f".{config['state_file'].name}.lifecycle.lock"
        )
        if state_lock == profile_lock:
            yield
        else:
            with exclusive_file_lock(state_lock):
                yield


def save_control(config, state, action):
    if action not in {"drain", "resume"}:
        raise ValueError(f"acción de control inválida: {action}")
    control_id = uuid.uuid4().hex
    save_json(config["control_file"], {
        "schema_version": CONTROL_SCHEMA_VERSION,
        "control_id": control_id,
        "action": action,
        "supervisor_pid": state["supervisor_pid"],
        "project": state["project"],
        "project_revision": state["project_revision"],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    return control_id


def load_control(config, supervisor_pid):
    path = config["control_file"]
    claimed_path = path.with_name(f".{path.name}.{supervisor_pid}.claimed")
    try:
        os.replace(path, claimed_path)
    except FileNotFoundError:
        return None
    try:
        control = json.loads(claimed_path.read_text(encoding="utf-8"))
        if control.get("schema_version") != CONTROL_SCHEMA_VERSION:
            raise ValueError("versión inválida del control de la granja")
        if not isinstance(control.get("control_id"), str):
            raise ValueError("el control no contiene un identificador válido")
        if control.get("supervisor_pid") != supervisor_pid:
            raise ValueError("el control pertenece a otro supervisor")
        if Path(control.get("project", "")).resolve() != config["project"]:
            raise ValueError("el control pertenece a otro proyecto")
        if control.get("project_revision") != config["project_revision"]:
            raise ValueError("el control pertenece a otra revisión del proyecto")
        if control.get("action") not in {"drain", "resume"}:
            raise ValueError("acción inválida en el control de la granja")
        return control
    finally:
        claimed_path.unlink(missing_ok=True)


def release_farm_leases(config, state=None):
    catalog = state_catalog(state, config) if state else config["catalog"]
    prefixes = (
        state_prefixes(state, config)
        if state
        else [coordinator["prefix"] for coordinator in config["coordinators"]]
    )
    workers = state_worker_count(state, config) if state else config["workers"]
    worker_names = set()
    for prefix in prefixes:
        worker_names.update(coordinator_worker_names(prefix, workers))
    if worker_names:
        release_catalog_workers(catalog, worker_names)


def farm_ack_file(config):
    return config.get(
        "ack_file",
        config["state_file"].with_name(f"{config['state_file'].stem}.ack.json"),
    )


def wait_for_control_ack(config, supervisor_pid, control_id):
    poll_seconds = config.get("poll_seconds", 5.0)
    deadline = time.monotonic() + max(5.0, poll_seconds * 2 + 1)
    while time.monotonic() < deadline:
        state = load_state(config["state_file"])
        if state and state.get("supervisor_pid") == supervisor_pid:
            if state.get("last_control_id") == control_id:
                return True
        ack_path = farm_ack_file(config)
        if ack_path.exists():
            acknowledgement = json.loads(ack_path.read_text(encoding="utf-8"))
            if (
                acknowledgement.get("supervisor_pid") == supervisor_pid
                and acknowledgement.get("control_id") == control_id
            ):
                return True
        if not state or not supervisor_is_alive(state):
            return False
        time.sleep(0.1)
    return False


def unlink_owned_state(config, supervisor_pid):
    state = load_state(config["state_file"])
    if state and state.get("supervisor_pid") == supervisor_pid:
        config["state_file"].unlink(missing_ok=True)


def active_state_process_groups(state):
    process_groups = []
    for child in state.get("children", []):
        process_group_id = child.get("pid")
        if not process_group_is_alive(process_group_id):
            continue
        token = child.get("token")
        if state.get("schema_version") == STATE_SCHEMA_VERSION:
            if not isinstance(token, str) or not token:
                raise RuntimeError(
                    f"el estado actual no identifica el grupo {process_group_id}"
                )
            ownership = process_group_has_token(process_group_id, token)
        else:
            ownership = legacy_coordinator_matches(child)
        if ownership is True:
            process_groups.append(process_group_id)
        else:
            raise RuntimeError(
                f"el grupo coordinador {process_group_id} no pudo verificarse"
            )
    return process_groups


def terminate_recorded_process_groups(state):
    process_groups = active_state_process_groups(state)
    for process_group_id in process_groups:
        try:
            os.killpg(process_group_id, signal.SIGTERM)
        except ProcessLookupError:
            pass
    deadline = time.monotonic() + 10
    while process_groups and time.monotonic() < deadline:
        active_groups = set(active_state_process_groups(state))
        process_groups = [
            process_group_id
            for process_group_id in process_groups
            if process_group_id in active_groups
        ]
        time.sleep(0.2)
    active_groups = set(active_state_process_groups(state))
    process_groups = [
        process_group_id
        for process_group_id in process_groups
        if process_group_id in active_groups
    ]
    for process_group_id in process_groups:
        try:
            os.killpg(process_group_id, signal.SIGKILL)
        except ProcessLookupError:
            pass
    kill_deadline = time.monotonic() + 2
    while process_groups and time.monotonic() < kill_deadline:
        active_groups = set(active_state_process_groups(state))
        process_groups = [
            process_group_id
            for process_group_id in process_groups
            if process_group_id in active_groups
        ]
        time.sleep(0.1)
    return process_groups


class FarmSupervisor:
    def __init__(self, config):
        self.config = config
        self.stop_requested = False
        self.draining = False
        self.last_control_id = None
        self.slots = [
            {
                "coordinator": coordinator,
                "process": None,
                "log": None,
                "cycles": 0,
                "failures": 0,
                "disabled": False,
                "token": None,
            }
            for coordinator in config["coordinators"]
        ]

    def request_stop(self, _signal_number, _frame):
        self.stop_requested = True

    def state_payload(self):
        supervisor_identity = process_identity(os.getpid())
        if supervisor_identity is None:
            raise RuntimeError("no se pudo identificar el proceso supervisor")
        return {
            "schema_version": STATE_SCHEMA_VERSION,
            "config": str(self.config["config_path"]),
            "project": str(self.config["project"]),
            "project_revision": self.config["project_revision"],
            "project_name": self.config["project_name"],
            "language": self.config["language"],
            "catalog": str(self.config["catalog"]),
            "workers": self.config["workers"],
            "supervisor_pid": os.getpid(),
            "supervisor_identity": supervisor_identity,
            "mode": "draining" if self.draining else "running",
            "last_control_id": self.last_control_id,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "children": [
                {
                    "prefix": slot["coordinator"]["prefix"],
                    "model": slot["coordinator"]["model"],
                    "pid": slot["process"].pid if slot["process"] else None,
                    "token": slot["token"],
                    "cycles": slot["cycles"],
                    "failures": slot["failures"],
                    "disabled": slot["disabled"],
                }
                for slot in self.slots
            ],
        }

    def save_state(self):
        save_json(self.config["state_file"], self.state_payload())

    def apply_control(self):
        control = load_control(self.config, os.getpid())
        action = control.get("action") if control else None
        if action == "drain":
            self.draining = True
            print("Drenado solicitado; no se iniciarán ciclos nuevos.", flush=True)
        elif action == "resume":
            self.draining = False
            print("Drenado cancelado; la granja continúa.", flush=True)
        if control:
            self.last_control_id = control["control_id"]
            self.save_state()
            save_json(farm_ack_file(self.config), {
                "schema_version": 1,
                "control_id": self.last_control_id,
                "action": action,
                "supervisor_pid": os.getpid(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            })

    def launch(self, slot):
        coordinator = slot["coordinator"]
        command = build_opencode_command(
            coordinator,
            self.config["project"],
            self.config["workers"],
            self.config["count"],
        )
        self.config["log_directory"].mkdir(parents=True, exist_ok=True)
        log_path = self.config["log_directory"] / f"{coordinator['prefix']}.log"
        log = log_path.open("a", encoding="utf-8", buffering=1)
        log.write(
            f"\n[{datetime.now(timezone.utc).isoformat()}] "
            f"cycle {slot['cycles'] + 1}: {' '.join(command)}\n"
        )
        try:
            environment = os.environ.copy()
            environment[WORKER_SCOPE_PREFIX_ENV] = coordinator["prefix"]
            environment[WORKER_SCOPE_COUNT_ENV] = str(self.config["workers"])
            environment[PROJECT_SCOPE_PATH_ENV] = str(self.config["project"])
            environment[PROJECT_SCOPE_REVISION_ENV] = self.config["project_revision"]
            slot["token"] = uuid.uuid4().hex
            environment[COORDINATOR_TOKEN_ENV] = slot["token"]
            process = subprocess.Popen(
                command,
                cwd=ROOT,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
                start_new_session=True,
            )
        except OSError:
            log.close()
            raise
        slot["process"] = process
        slot["log"] = log
        slot["cycles"] += 1
        print(
            f"Iniciado {coordinator['prefix']} con {coordinator['model']} "
            f"(PID {process.pid}, ciclo {slot['cycles']})",
            flush=True,
        )
        self.save_state()

    def close_finished_slot(self, slot):
        process = slot["process"]
        if process is None or process.poll() is None:
            return
        if slot_process_group_is_alive(slot):
            return
        return_code = process.returncode
        if slot["log"]:
            slot["log"].write(
                f"[{datetime.now(timezone.utc).isoformat()}] "
                f"process exited with {return_code}\n"
            )
            slot["log"].close()
        slot["process"] = None
        slot["log"] = None
        slot["token"] = None
        if return_code == 0:
            slot["failures"] = 0
            return

        slot["failures"] += 1
        print(
            f"{slot['coordinator']['prefix']} terminó con código {return_code} "
            f"(fallo {slot['failures']}/{self.config['max_restarts'] + 1})",
            flush=True,
        )
        if slot["failures"] > self.config["max_restarts"]:
            slot["disabled"] = True
            release_catalog_workers(
                self.config["catalog"],
                coordinator_worker_names(
                    slot["coordinator"]["prefix"], self.config["workers"]
                ),
            )

    def terminate_children(self):
        tracked = [
            slot for slot in self.slots
            if slot["process"] is not None
        ]
        process_groups = [
            slot["process"].pid
            for slot in tracked
            if slot_process_group_is_alive(slot)
        ]
        for process_group_id in process_groups:
            try:
                os.killpg(process_group_id, signal.SIGTERM)
            except ProcessLookupError:
                pass
        deadline = time.monotonic() + 10
        while process_groups and time.monotonic() < deadline:
            for slot in tracked:
                slot["process"].poll()
            active_groups = {
                slot["process"].pid
                for slot in tracked
                if slot_process_group_is_alive(slot)
            }
            process_groups = [
                process_group_id
                for process_group_id in process_groups
                if process_group_id in active_groups
            ]
            time.sleep(0.2)
        active_groups = {
            slot["process"].pid
            for slot in tracked
            if slot_process_group_is_alive(slot)
        }
        process_groups = [
            process_group_id
            for process_group_id in process_groups
            if process_group_id in active_groups
        ]
        for process_group_id in process_groups:
            try:
                os.killpg(process_group_id, signal.SIGKILL)
            except ProcessLookupError:
                pass
        kill_deadline = time.monotonic() + 2
        while process_groups and time.monotonic() < kill_deadline:
            for slot in tracked:
                slot["process"].poll()
            active_groups = {
                slot["process"].pid
                for slot in tracked
                if slot_process_group_is_alive(slot)
            }
            process_groups = [
                process_group_id
                for process_group_id in process_groups
                if process_group_id in active_groups
            ]
            time.sleep(0.1)
        if process_groups:
            raise RuntimeError(
                "no se pudieron detener todos los grupos de coordinadores"
            )
        for slot in tracked:
            try:
                slot["process"].wait(timeout=2)
            except subprocess.TimeoutExpired:
                pass
        for slot in self.slots:
            if slot["log"]:
                slot["log"].close()
                slot["log"] = None
            slot["process"] = None
            slot["token"] = None

    def cleanup(self):
        self.terminate_children()
        release_farm_leases(self.config)
        unlink_owned_state(self.config, os.getpid())
        self.config["control_file"].unlink(missing_ok=True)

    def prepare(self):
        self.config["state_file"].parent.mkdir(parents=True, exist_ok=True)
        self.config["control_file"].parent.mkdir(parents=True, exist_ok=True)
        self.config["control_file"].unlink(missing_ok=True)
        farm_ack_file(self.config).unlink(missing_ok=True)
        self.save_state()

    def run(self, prepared=False):
        signal.signal(signal.SIGINT, self.request_stop)
        signal.signal(signal.SIGTERM, self.request_stop)

        try:
            if not prepared:
                self.prepare()
            while True:
                self.apply_control()
                if self.stop_requested:
                    print("Deteniendo granja y liberando leases...", flush=True)
                    return 0

                if project_revision(self.config["project"]) != self.config["project_revision"]:
                    raise RuntimeError(
                        "la configuración del proyecto cambió durante la ejecución"
                    )

                for slot in self.slots:
                    self.close_finished_slot(slot)

                snapshot = catalog_progress_snapshot(
                    self.config["catalog"],
                    "incomplete",
                    self.config["project_name"],
                    self.config["language"],
                )
                if snapshot["eligible"] == 0:
                    print("Cola de traducción completa.", flush=True)
                    return 0

                running = any(
                    slot_process_group_is_alive(slot)
                    for slot in self.slots
                )
                if self.draining:
                    self.save_state()
                    if not running:
                        print("Drenado completo; la granja queda detenida.", flush=True)
                        return 0
                    time.sleep(self.config["poll_seconds"])
                    continue

                enabled = [slot for slot in self.slots if not slot["disabled"]]
                if not enabled:
                    print("Todos los coordinadores quedaron deshabilitados.", flush=True)
                    return 1

                if snapshot["available"] > 0:
                    for slot in enabled:
                        if slot["process"] is None:
                            self.launch(slot)
                elif not running:
                    owned = [
                        batch for batch in snapshot["active_batches"]
                        if any(
                            batch["worker"] == coordinator["prefix"]
                            or batch["worker"].startswith(
                                f"{coordinator['prefix']}-"
                            )
                            for coordinator in self.config["coordinators"]
                        )
                    ]
                    if owned:
                        print("Limpiando leases huérfanos de la granja...", flush=True)
                        release_farm_leases(self.config)

                self.save_state()
                time.sleep(self.config["poll_seconds"])
        finally:
            self.cleanup()


def print_dry_run(config):
    for coordinator in config["coordinators"]:
        print(" ".join(build_opencode_command(
            coordinator,
            config["project"],
            config["workers"],
            config["count"],
        )))


def prepare_start_locked(config):
    state = load_state(config["state_file"])
    if state and supervisor_is_alive(state):
        raise RuntimeError(
            f"la granja ya está activa con PID {state['supervisor_pid']}"
        )
    if state:
        validate_state_owner(state, config)
        if active_state_process_groups(state):
            raise RuntimeError(
                "persisten coordinadores sin supervisor; use stop antes de iniciar"
            )
        release_farm_leases(config, state)
        config["state_file"].unlink(missing_ok=True)
    config["control_file"].unlink(missing_ok=True)
    farm_ack_file(config).unlink(missing_ok=True)


def cleanup_failed_detached_start(config, process):
    if process.poll() is None:
        try:
            os.kill(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired as error:
                raise RuntimeError(
                    "el supervisor fallido no pudo detenerse; no se liberaron leases"
                ) from error

    state = load_state(config["state_file"])
    if state and state.get("supervisor_pid") == process.pid:
        remaining_groups = terminate_recorded_process_groups(state)
        if remaining_groups:
            raise RuntimeError(
                "el arranque falló y quedaron coordinadores; no se liberaron leases"
            )
        release_farm_leases(config, state)
        unlink_owned_state(config, process.pid)
    config["control_file"].unlink(missing_ok=True)
    farm_ack_file(config).unlink(missing_ok=True)


def start_detached_locked(config):
    if shutil.which("opencode") is None:
        raise RuntimeError("no se encontró opencode en PATH")
    config["log_directory"].mkdir(parents=True, exist_ok=True)
    supervisor_log = config["log_directory"] / "supervisor.log"
    environment = os.environ.copy()
    environment[SUPERVISOR_CHILD_ENV] = "1"
    environment[PROJECT_SCOPE_PATH_ENV] = str(config["project"])
    environment[PROJECT_SCOPE_REVISION_ENV] = config["project_revision"]
    with supervisor_log.open("a", encoding="utf-8") as log:
        process = subprocess.Popen(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                "start",
                "--config",
                str(config["config_path"]),
            ],
            cwd=ROOT,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )

    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            state = load_state(config["state_file"])
            if state and state.get("supervisor_pid") == process.pid:
                validate_state_identity(state, config)
                if not supervisor_is_alive(state):
                    break
                print(f"Granja iniciada en segundo plano (PID {process.pid})")
                print(f"Log del supervisor: {supervisor_log}")
                return 0
            if process.poll() is not None:
                break
            time.sleep(0.05)
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError):
        cleanup_failed_detached_start(config, process)
        raise

    cleanup_failed_detached_start(config, process)
    raise RuntimeError(f"el supervisor no pudo iniciar; revise {supervisor_log}")


def start_farm(config, detach, dry_run):
    if dry_run:
        print_dry_run(config)
        return 0
    if config.get("runtime_fallback"):
        raise RuntimeError(
            "repare el perfil antes de iniciar una granja"
        )
    if shutil.which("opencode") is None:
        raise RuntimeError("no se encontró opencode en PATH")
    if os.environ.pop(SUPERVISOR_CHILD_ENV, None) == "1":
        if detach:
            raise RuntimeError("un supervisor hijo no puede volver a separarse")
        return FarmSupervisor(config).run()

    supervisor = None
    with farm_lifecycle_lock(config):
        prepare_start_locked(config)
        if detach:
            return start_detached_locked(config)
        supervisor = FarmSupervisor(config)
        supervisor.prepare()

    return supervisor.run(prepared=True)


def stop_farm(config):
    with farm_lifecycle_lock(config):
        state = load_state(config["state_file"])
        if state:
            validate_state_owner(state, config)
        if state and supervisor_is_alive(state):
            supervisor_pid = state["supervisor_pid"]
            try:
                os.kill(supervisor_pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            if not wait_for_process_exit(
                supervisor_pid, 30, state.get("supervisor_identity")
            ):
                raise RuntimeError(
                    "el supervisor no se detuvo; los leases no fueron liberados"
                )
        remaining_groups = terminate_recorded_process_groups(state) if state else []
        if remaining_groups:
            raise RuntimeError(
                "persisten procesos coordinadores; los leases no fueron liberados"
            )
        release_farm_leases(config, state)
        if state:
            unlink_owned_state(config, state.get("supervisor_pid"))
        config["control_file"].unlink(missing_ok=True)
        farm_ack_file(config).unlink(missing_ok=True)
        if config.get("runtime_anchor_file"):
            config["runtime_anchor_file"].unlink(missing_ok=True)
    print("Granja detenida y leases liberados.")
    return 0


def clean_farm(config):
    with farm_lifecycle_lock(config):
        state = load_state(config["state_file"])
        if state:
            validate_state_owner(state, config)
        if state and supervisor_is_alive(state):
            raise RuntimeError("la granja está activa; use stop en lugar de clean")
        remaining_groups = active_state_process_groups(state) if state else []
        if remaining_groups:
            raise RuntimeError(
                "persisten procesos coordinadores; use stop antes de limpiar"
            )
        release_farm_leases(config, state)
        if state:
            unlink_owned_state(config, state.get("supervisor_pid"))
        config["control_file"].unlink(missing_ok=True)
        farm_ack_file(config).unlink(missing_ok=True)
        if config.get("runtime_anchor_file"):
            config["runtime_anchor_file"].unlink(missing_ok=True)
    print("Leases huérfanos liberados.")
    return 0


def drain_farm(config):
    with farm_lifecycle_lock(config):
        state = load_state(config["state_file"])
        if not state or not supervisor_is_alive(state):
            raise RuntimeError("la granja no está activa")
        if state.get("schema_version") != STATE_SCHEMA_VERSION:
            raise RuntimeError(
                "el supervisor es antiguo; deténgalo y vuelva a iniciarlo"
            )
        validate_state_identity(state, config)
        control_id = save_control(config, state, "drain")
        acknowledged = wait_for_control_ack(
            config, state["supervisor_pid"], control_id
        )
        if not acknowledged:
            raise RuntimeError("el supervisor no confirmó el drenado")
    print("Drenado solicitado; se completará la ronda activa.")
    return 0


def resume_farm(config):
    with farm_lifecycle_lock(config):
        state = load_state(config["state_file"])
        if state:
            validate_state_owner(state, config)
        if state and supervisor_is_alive(state):
            if state.get("schema_version") != STATE_SCHEMA_VERSION:
                raise RuntimeError(
                    "el supervisor es antiguo; deténgalo y vuelva a iniciarlo"
                )
            validate_state_identity(state, config)
            control_id = save_control(config, state, "resume")
            if wait_for_control_ack(config, state["supervisor_pid"], control_id):
                print("Reanudación solicitada.")
                return 0
            if supervisor_is_alive(state):
                raise RuntimeError("el supervisor no confirmó la reanudación")

        if config.get("runtime_fallback"):
            raise RuntimeError(
                "repare el perfil antes de reiniciar una granja detenida"
            )
        if state:
            if active_state_process_groups(state):
                raise RuntimeError(
                    "persisten coordinadores sin supervisor; use stop antes de reanudar"
                )
            release_farm_leases(config, state)
            unlink_owned_state(config, state.get("supervisor_pid"))
        config["control_file"].unlink(missing_ok=True)
        return start_detached_locked(config)


def farm_status(config):
    bind_runtime_paths(config, create=False)
    state = load_state(config["state_file"])
    supervisor_active = bool(state and supervisor_is_alive(state))
    process_groups = active_state_process_groups(state) if state else []
    orphaned = bool(process_groups and not supervisor_active)
    active = supervisor_active or orphaned
    if state:
        validate_state_owner(state, config)
    project_changed = bool(
        active
        and (
            Path(state.get("project", "")).resolve() != config["project"]
            or state.get("project_revision") != config["project_revision"]
            or (
                state.get("catalog")
                and Path(state["catalog"]).resolve() != config["catalog"]
            )
        )
    )
    children = []
    active_group_ids = set(process_groups)
    if state:
        for child in state.get("children", []):
            children.append({
                **{key: value for key, value in child.items() if key != "token"},
                "active": child.get("pid") in active_group_ids,
            })
    snapshot = catalog_progress_snapshot(
        state_catalog(state, config) if active else config["catalog"],
        "incomplete",
        state.get("project_name", config["project_name"])
        if active
        else config["project_name"],
        state.get("language", config["language"])
        if active
        else config["language"],
    )
    return {
        "supervisor": {
            "active": active,
            "pid": state.get("supervisor_pid") if state else None,
            "mode": "orphaned" if orphaned else (
                state.get("mode", "stopped") if active else "stopped"
            ),
            "orphaned": orphaned,
            "project_changed": project_changed,
            "profile_available": not config.get("runtime_fallback", False),
            "control_supported": bool(
                not active
                or (
                    not orphaned
                    and state.get("schema_version") == STATE_SCHEMA_VERSION
                )
            ),
        },
        "children": children,
        "queue": snapshot,
    }


def show_status(config, as_json=False):
    result = farm_status(config)
    supervisor = result["supervisor"]
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if not supervisor["active"]:
        print("Supervisor: inactivo")
    else:
        print(
            f"Supervisor: activo (PID {supervisor['pid']}, "
            f"modo={supervisor['mode']})"
        )
        if supervisor["project_changed"]:
            print("  Advertencia: el proyecto cambió; detenga la granja.")
        if supervisor["orphaned"]:
            print("  Advertencia: hay coordinadores sin supervisor; use stop.")
        for child in result["children"]:
            print(
                f"  {child['prefix']}: {'activo' if child['active'] else 'esperando'} "
                f"modelo={child['model']} ciclos={child['cycles']} "
                f"fallos={child['failures']}"
            )
    snapshot = result["queue"]
    print(
        f"Cola: {snapshot['eligible']} incompletas, {snapshot['reserved']} "
        f"reservadas, {snapshot['available']} disponibles"
    )
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Supervisa múltiples coordinadores OpenCode de traducción."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("start", "stop", "clean", "status", "drain", "resume"):
        command_parser = subparsers.add_parser(command)
        command_parser.add_argument("--config", required=True, type=Path)
        if command == "start":
            command_parser.add_argument("--detach", action="store_true")
            command_parser.add_argument("--dry-run", action="store_true")
        if command == "status":
            command_parser.add_argument("--json", action="store_true")

    args = parser.parse_args()
    try:
        config = (
            load_farm_config(args.config)
            if args.command == "start"
            else load_farm_config_with_runtime_fallback(args.config)
        )
        if args.command == "start":
            return start_farm(config, args.detach, args.dry_run)
        if args.command == "stop":
            return stop_farm(config)
        if args.command == "clean":
            return clean_farm(config)
        if args.command == "drain":
            return drain_farm(config)
        if args.command == "resume":
            return resume_farm(config)
        return show_status(config, args.json)
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
