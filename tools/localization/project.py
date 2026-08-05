#!/usr/bin/env python3

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
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


def load_project(path):
    project_path = Path(path)
    with project_path.open(encoding="utf-8") as project_file:
        project = json.load(project_file)

    missing = sorted(REQUIRED_FIELDS - project.keys())
    if missing:
        raise ValueError(f"Faltan campos del proyecto: {', '.join(missing)}")
    if not isinstance(project["string_files"], list) or not project["string_files"]:
        raise ValueError("string_files debe ser una lista no vacía")
    return project


def resolve_project_path(project, field):
    return ROOT / project[field]
