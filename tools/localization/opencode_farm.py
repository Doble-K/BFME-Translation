#!/usr/bin/env python3

import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from agent_batch import (
    WORKER_SCOPE_COUNT_ENV,
    WORKER_SCOPE_PREFIX_ENV,
    release_prefix,
    save_json,
)
from project import (
    PROJECT_SCOPE_PATH_ENV,
    PROJECT_SCOPE_REVISION_ENV,
    canonical_project_path,
    project_revision,
)
from watch_progress import progress_snapshot


ROOT = Path(__file__).resolve().parents[2]
STATE_SCHEMA_VERSION = 1
PREFIX_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,55}$")


def resolve_root_path(value):
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


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
    if not isinstance(workers, int) or not 2 <= workers <= 8:
        raise ValueError("workers debe estar entre 2 y 8")
    if not isinstance(count, int) or not 1 <= count <= 100:
        raise ValueError("count debe estar entre 1 y 100")
    if not isinstance(max_restarts, int) or not 0 <= max_restarts <= 10:
        raise ValueError("max_restarts debe estar entre 0 y 10")
    if not isinstance(poll_seconds, (int, float)) or poll_seconds < 1:
        raise ValueError("poll_seconds debe ser de al menos 1 segundo")

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

    project_path = canonical_project_path(
        resolve_root_path(data.get("project", "config/project.json"))
    )
    return {
        "config_path": config_path,
        "project": project_path,
        "project_revision": project_revision(project_path),
        "workers": workers,
        "count": count,
        "max_restarts": max_restarts,
        "poll_seconds": float(poll_seconds),
        "state_file": resolve_root_path(
            data.get("state_file", ".agent/opencode-farm-state.json")
        ),
        "log_directory": resolve_root_path(
            data.get("log_directory", ".agent/logs/opencode-farm")
        ),
        "coordinators": normalized,
    }


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


def wait_for_process_exit(pid, timeout):
    deadline = time.monotonic() + timeout
    while process_is_alive(pid):
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.2)
    return True


def load_state(path):
    if not path.exists():
        return None
    state = json.loads(path.read_text(encoding="utf-8"))
    if state.get("schema_version") != STATE_SCHEMA_VERSION:
        raise ValueError("versión inválida del estado de la granja")
    return state


def release_farm_leases(config):
    for coordinator in config["coordinators"]:
        release_prefix(config["project"], coordinator["prefix"])


class FarmSupervisor:
    def __init__(self, config):
        self.config = config
        self.stop_requested = False
        self.slots = [
            {
                "coordinator": coordinator,
                "process": None,
                "log": None,
                "cycles": 0,
                "failures": 0,
                "disabled": False,
            }
            for coordinator in config["coordinators"]
        ]

    def request_stop(self, _signal_number, _frame):
        self.stop_requested = True

    def state_payload(self):
        return {
            "schema_version": STATE_SCHEMA_VERSION,
            "config": str(self.config["config_path"]),
            "project": str(self.config["project"]),
            "project_revision": self.config["project_revision"],
            "supervisor_pid": os.getpid(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "children": [
                {
                    "prefix": slot["coordinator"]["prefix"],
                    "model": slot["coordinator"]["model"],
                    "pid": slot["process"].pid if slot["process"] else None,
                    "cycles": slot["cycles"],
                    "failures": slot["failures"],
                    "disabled": slot["disabled"],
                }
                for slot in self.slots
            ],
        }

    def save_state(self):
        save_json(self.config["state_file"], self.state_payload())

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
        return_code = process.returncode
        if slot["log"]:
            slot["log"].write(
                f"[{datetime.now(timezone.utc).isoformat()}] "
                f"process exited with {return_code}\n"
            )
            slot["log"].close()
        slot["process"] = None
        slot["log"] = None
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
            release_prefix(self.config["project"], slot["coordinator"]["prefix"])

    def terminate_children(self):
        running = [
            slot for slot in self.slots
            if slot["process"] is not None and slot["process"].poll() is None
        ]
        for slot in running:
            try:
                os.killpg(slot["process"].pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        deadline = time.monotonic() + 10
        while running and time.monotonic() < deadline:
            running = [slot for slot in running if slot["process"].poll() is None]
            time.sleep(0.2)
        for slot in running:
            try:
                os.killpg(slot["process"].pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        for slot in running:
            try:
                slot["process"].wait(timeout=2)
            except subprocess.TimeoutExpired:
                pass
        for slot in self.slots:
            if slot["log"]:
                slot["log"].close()
                slot["log"] = None
            slot["process"] = None

    def cleanup(self):
        self.terminate_children()
        release_farm_leases(self.config)
        self.config["state_file"].unlink(missing_ok=True)

    def run(self):
        signal.signal(signal.SIGINT, self.request_stop)
        signal.signal(signal.SIGTERM, self.request_stop)
        self.config["state_file"].parent.mkdir(parents=True, exist_ok=True)

        try:
            self.save_state()
            while True:
                if self.stop_requested:
                    print("Deteniendo granja y liberando leases...", flush=True)
                    return 0

                for slot in self.slots:
                    self.close_finished_slot(slot)

                snapshot = progress_snapshot(self.config["project"], "incomplete")
                if snapshot["eligible"] == 0:
                    print("Cola de traducción completa.", flush=True)
                    return 0

                running = any(
                    slot["process"] is not None
                    and slot["process"].poll() is None
                    for slot in self.slots
                )
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


def start_farm(config, detach, dry_run):
    if dry_run:
        print_dry_run(config)
        return 0
    if shutil.which("opencode") is None:
        raise RuntimeError("no se encontró opencode en PATH")

    state = load_state(config["state_file"])
    if state and process_is_alive(state.get("supervisor_pid")):
        raise RuntimeError(
            f"la granja ya está activa con PID {state['supervisor_pid']}"
        )
    if state:
        config["state_file"].unlink(missing_ok=True)

    if not detach:
        return FarmSupervisor(config).run()

    config["log_directory"].mkdir(parents=True, exist_ok=True)
    supervisor_log = config["log_directory"] / "supervisor.log"
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
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
    print(f"Granja iniciada en segundo plano (PID {process.pid})")
    print(f"Log del supervisor: {supervisor_log}")
    return 0


def stop_farm(config):
    state = load_state(config["state_file"])
    if state and process_is_alive(state.get("supervisor_pid")):
        supervisor_pid = state["supervisor_pid"]
        try:
            os.kill(supervisor_pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        if not wait_for_process_exit(supervisor_pid, 30):
            raise RuntimeError(
                "el supervisor no se detuvo; los leases no fueron liberados"
            )
    release_farm_leases(config)
    config["state_file"].unlink(missing_ok=True)
    print("Granja detenida y leases liberados.")
    return 0


def clean_farm(config):
    state = load_state(config["state_file"])
    if state and process_is_alive(state.get("supervisor_pid")):
        raise RuntimeError("la granja está activa; use stop en lugar de clean")
    release_farm_leases(config)
    config["state_file"].unlink(missing_ok=True)
    print("Leases huérfanos liberados.")
    return 0


def show_status(config):
    state = load_state(config["state_file"])
    if not state:
        print("Supervisor: inactivo")
    else:
        alive = process_is_alive(state.get("supervisor_pid"))
        print(
            f"Supervisor: {'activo' if alive else 'inactivo'} "
            f"(PID {state.get('supervisor_pid')})"
        )
        for child in state.get("children", []):
            child_alive = process_is_alive(child.get("pid"))
            print(
                f"  {child['prefix']}: {'activo' if child_alive else 'esperando'} "
                f"modelo={child['model']} ciclos={child['cycles']} "
                f"fallos={child['failures']}"
            )
    snapshot = progress_snapshot(config["project"], "incomplete")
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
    for command in ("start", "stop", "clean", "status"):
        command_parser = subparsers.add_parser(command)
        command_parser.add_argument("--config", required=True, type=Path)
        if command == "start":
            command_parser.add_argument("--detach", action="store_true")
            command_parser.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()
    try:
        config = load_farm_config(args.config)
        if args.command == "start":
            return start_farm(config, args.detach, args.dry_run)
        if args.command == "stop":
            return stop_farm(config)
        if args.command == "clean":
            return clean_farm(config)
        return show_status(config)
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
