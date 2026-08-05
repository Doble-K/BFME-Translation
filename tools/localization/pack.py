#!/usr/bin/env python3

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from project import load_project, resolve_project_path
from extract import extract_str


ROOT = Path(__file__).resolve().parents[2]


def verify_embedded_files(
    big4f, package_path, package_dir, expected_files, debug, debug_ids, debug_marker
):
    with tempfile.TemporaryDirectory(prefix="localization-pack-verify-") as verification_dir:
        verification_root = Path(verification_dir)
        subprocess.run(
            [str(big4f.resolve()), "x", str(package_path.resolve()), str(verification_root)],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        for relative_path in expected_files:
            source_file = package_dir / relative_path
            embedded_file = verification_root / relative_path
            if not embedded_file.is_file():
                raise ValueError(f"El paquete no contiene {relative_path}.")
            if source_file.read_bytes() != embedded_file.read_bytes():
                raise ValueError(f"El contenido empaquetado difiere en {relative_path}.")

            if source_file.suffix.lower() != ".str":
                continue
            source_entries = extract_str(source_file)
            embedded_entries = extract_str(embedded_file)
            source_ids = [entry["id"] for entry in source_entries]
            embedded_ids = [entry["id"] for entry in embedded_entries]
            if source_ids != embedded_ids:
                raise ValueError(f"Los IDs empaquetados difieren en {relative_path}.")
            if len(source_entries) != len(embedded_entries):
                raise ValueError(f"La cantidad de entradas difiere en {relative_path}.")

            if debug_ids:
                markers = [
                    entry["text"]
                    for entry in embedded_entries
                    if entry["id"] in debug_ids
                ]
                has_debug_marker = debug_marker in markers
                if debug != has_debug_marker:
                    expected = debug_marker if debug else "la traduccion normal"
                    raise ValueError(
                        f"Marcador inesperado en {relative_path}: se esperaba {expected}."
                    )

            print(
                f"Contenido verificado: {relative_path} "
                f"({len(embedded_entries)} entradas, IDs y bytes coinciden)."
            )


def main():
    parser = argparse.ArgumentParser(description="Pack a configured SAGE localization release.")
    parser.add_argument(
        "--exclude-orphan-ids",
        action="store_true",
        help="Debug build excluding IDs made only of whitespace",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Replace configured debug IDs with the configured marker",
    )
    parser.add_argument(
        "--dedupe-ids",
        choices=("first", "last"),
        help="Debug build keeping the first or last non-whitespace ID",
    )
    parser.add_argument("--project", help="Project configuration JSON")
    args = parser.parse_args()

    project = None
    if not args.project:
        print(
            "Error: pack.py requiere --project para conocer las rutas y archivos del proyecto.",
            file=sys.stderr,
        )
        return 2
    try:
        project = load_project(args.project)
    except (OSError, ValueError) as error:
        print(f"Error: configuración de proyecto inválida: {error}", file=sys.stderr)
        return 1

    big4f = ROOT / "tools" / "big4f" / "bin"
    platform_name = sys.platform
    if platform_name.startswith("linux"):
        big4f /= Path("linux") / "big4f"
    elif platform_name.startswith("win"):
        big4f /= Path("windows") / "big4f.exe"
    elif platform_name == "darwin":
        big4f /= Path("macos") / "big4f"
    else:
        big4f = None

    if not big4f or not big4f.exists():
        print(f"Error: No se encontró el binario de big4f para '{platform_name}' en {big4f}")
        return 1

    source_dir = resolve_project_path(project, "string_directory")
    output_release = resolve_project_path(project, "output_package")
    expected_files = project["string_files"]
    debug_ids = set(project.get("debug_ids", []))
    debug_marker = project.get("debug_marker", "DEBUGING")
    output_release.parent.mkdir(parents=True, exist_ok=True)

    debug_build = args.exclude_orphan_ids or args.debug or args.dedupe_ids
    with tempfile.TemporaryDirectory(prefix="localization-pack-") as temporary_dir:
        package_dir = source_dir
        if debug_build:
            package_dir = Path(temporary_dir) / "project"
            shutil.copytree(source_dir, package_dir)
            if len(expected_files) != 1:
                print(
                    "Error: las builds debug actuales requieren un único archivo string.",
                    file=sys.stderr,
                )
                return 1
            debug_str = package_dir / expected_files[0]
            build_command = [
                sys.executable,
                str(ROOT / "tools" / "localization" / "build.py"),
                str(resolve_project_path(project, "catalog")),
                str(debug_str),
                "--allow-source-fallback",
            ]
            if args.project:
                build_command.extend(("--project", args.project))
            if args.exclude_orphan_ids:
                build_command.append("--exclude-whitespace-ids")
            if args.debug:
                build_command.append("--debug")
            if args.dedupe_ids:
                build_command.extend(("--dedupe-ids", args.dedupe_ids))
            try:
                subprocess.run(build_command, cwd=ROOT, check=True)
            except subprocess.CalledProcessError as error:
                print(f"Error durante la build debug: {error}")
                return error.returncode or 1

        for relative_path in expected_files:
            source_str = package_dir / relative_path
            if not source_str.is_file() or source_str.stat().st_size == 0:
                print(
                    f"Error: no se encontró un archivo string válido en {source_str}.",
                    file=sys.stderr,
                )
                return 1

        print(f"Empaquetando {package_dir} usando {big4f}...")
        try:
            subprocess.run(
                [str(big4f.resolve()), "f", ".", str(output_release.resolve())],
                cwd=package_dir,
                check=True,
            )
        except subprocess.CalledProcessError as error:
            print(f"Error durante el empaquetado con big4f: {error}")
            return error.returncode or 1

        if not output_release.is_file() or output_release.stat().st_size == 0:
            print("Error: big4f no generó un paquete válido.", file=sys.stderr)
            return 1

        try:
            listing = subprocess.run(
                [str(big4f.resolve()), "l", str(output_release.resolve())],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            ).stdout
        except subprocess.CalledProcessError as error:
            print(f"Error verificando el contenido del paquete: {error}", file=sys.stderr)
            return error.returncode or 1

        normalized_listing = listing.replace("\\", "/").lower()
        for relative_path in expected_files:
            expected_path = relative_path.replace("\\", "/").lower()
            if expected_path not in normalized_listing:
                print(
                    f"Error: el paquete no contiene {relative_path}.",
                    file=sys.stderr,
                )
                return 1
            print(f"Verificación del paquete: {relative_path} encontrada.")

        try:
            verify_embedded_files(
                big4f,
                output_release,
                package_dir,
                expected_files,
                args.debug,
                debug_ids,
                debug_marker,
            )
        except (OSError, ValueError, subprocess.CalledProcessError) as error:
            print(f"Error en la verificación profunda del paquete: {error}", file=sys.stderr)
            return 1

        if args.exclude_orphan_ids:
            print("Modo debug: se excluyeron IDs compuestos solo por espacios.")
    if args.debug:
        print(f"Modo debug: se aplicó el marcador {debug_marker}.")
    if args.dedupe_ids:
        print(f"Modo debug: se conservaron IDs duplicados con política '{args.dedupe_ids}'.")
    print(f"¡Empaquetado exitoso! Archivo generado en: {output_release}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
