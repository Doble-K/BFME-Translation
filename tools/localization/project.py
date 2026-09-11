#!/usr/bin/env python3

import hashlib
import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_GLOSSARY = ROOT / "GLOSSARY.md"
PROJECT_SCOPE_PATH_ENV = "SAGE_LOCALIZATION_PROJECT"
PROJECT_SCOPE_REVISION_ENV = "SAGE_LOCALIZATION_PROJECT_REVISION"
REQUIRED_FIELDS = {
    "name",
    "string_directory",
    "string_files",
    "catalog",
    "output_string_file",
    "output_package",
    "language",
    "encoding",
}


def canonical_project_path(path):
    return Path(path).expanduser().resolve(strict=True)


def project_revision(path):
    return hashlib.md5(
        canonical_project_path(path).read_bytes(), usedforsecurity=False
    ).hexdigest()


def validate_project_scope(path):
    expected_path_text = os.environ.get(PROJECT_SCOPE_PATH_ENV)
    expected_revision = os.environ.get(PROJECT_SCOPE_REVISION_ENV)
    if expected_path_text is None and expected_revision is None:
        return
    if not expected_path_text or not expected_revision:
        raise ValueError("el ámbito supervisado del proyecto está incompleto")

    actual_path = canonical_project_path(path)
    expected_path = canonical_project_path(expected_path_text)
    if actual_path != expected_path:
        raise ValueError(
            f"proyecto fuera del ámbito supervisado: {actual_path}; "
            f"se esperaba {expected_path}"
        )
    actual_revision = project_revision(actual_path)
    if actual_revision != expected_revision:
        raise ValueError(
            "la configuración del proyecto cambió durante la ejecución supervisada"
        )


def load_project(path):
    project_path = canonical_project_path(path)
    validate_project_scope(project_path)
    with project_path.open(encoding="utf-8") as project_file:
        project = json.load(project_file)

    missing = sorted(REQUIRED_FIELDS - project.keys())
    if missing:
        raise ValueError(f"Faltan campos del proyecto: {', '.join(missing)}")
    if not isinstance(project["string_files"], list) or not project["string_files"]:
        raise ValueError("string_files debe ser una lista no vacía")
    if "string_header" in project and not isinstance(project["string_header"], str):
        raise ValueError("string_header debe ser una cadena")
    if "debug_ids" in project and (
        not isinstance(project["debug_ids"], list)
        or not all(isinstance(entry_id, str) for entry_id in project["debug_ids"])
    ):
        raise ValueError("debug_ids debe ser una lista de cadenas")
    if "debug_marker" in project and not isinstance(project["debug_marker"], str):
        raise ValueError("debug_marker debe ser una cadena")
    if "glossary" in project and not isinstance(project["glossary"], str):
        raise ValueError("glossary debe ser una cadena")
    return project


def resolve_project_path(project, field):
    return ROOT / project[field]


def resolve_glossary_path(project):
    """Resolve the glossary path for a project.

    If the project contains a ``glossary`` field, resolve it relative to the
    project root.  Otherwise fall back to the default root-level GLOSSARY.md.
    """
    glossary_rel = project.get("glossary")
    if glossary_rel:
        candidate = ROOT / glossary_rel
        if candidate.is_file():
            return candidate
    return DEFAULT_GLOSSARY
