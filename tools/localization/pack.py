#!/usr/bin/env python3

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description="Pack the Spanish localization release.")
    parser.add_argument(
        "--exclude-orphan-ids",
        action="store_true",
        help="Debug build excluding IDs made only of whitespace",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Replace the single-player labels with the debug marker",
    )
    parser.add_argument(
        "--dedupe-ids",
        choices=("first", "last"),
        help="Debug build keeping the first or last non-whitespace ID",
    )
    args = parser.parse_args()

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

    source_dir = ROOT / "translations" / "spanish"
    output_release = ROOT / "releases" / "spanishpatch202.big"
    output_release.parent.mkdir(parents=True, exist_ok=True)

    debug_build = args.exclude_orphan_ids or args.debug or args.dedupe_ids
    with tempfile.TemporaryDirectory(prefix="spanishpack-") as temporary_dir:
        package_dir = source_dir
        if debug_build:
            package_dir = Path(temporary_dir) / "spanish"
            shutil.copytree(source_dir, package_dir)
            debug_str = package_dir / "data" / "lotr.str"
            build_command = [
                sys.executable,
                str(ROOT / "tools" / "localization" / "build.py"),
                str(ROOT / "catalogs" / "spanish_work.json"),
                str(debug_str),
                "--allow-source-fallback",
            ]
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

        source_str = package_dir / "data" / "lotr.str"
        if not source_str.is_file() or source_str.stat().st_size == 0:
            print(f"Error: no se encontró un lotr.str válido en {source_str}.", file=sys.stderr)
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
        if "data/lotr.str" not in normalized_listing:
            print("Error: el paquete no contiene data/lotr.str.", file=sys.stderr)
            return 1
        print("Verificación del paquete: data/lotr.str encontrada.")

        if args.exclude_orphan_ids:
            print("Modo debug: se excluyeron IDs compuestos solo por espacios.")
    if args.debug:
        print("Modo debug: se aplicó el marcador DEBUGING.")
    if args.dedupe_ids:
        print(f"Modo debug: se conservaron IDs duplicados con política '{args.dedupe_ids}'.")
    print(f"¡Empaquetado exitoso! Archivo generado en: {output_release}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
