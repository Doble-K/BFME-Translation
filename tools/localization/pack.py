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

    debug_build = args.exclude_orphan_ids or args.debug
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
            ]
            if args.exclude_orphan_ids:
                build_command.append("--exclude-whitespace-ids")
            if args.debug:
                build_command.append("--debug")
            try:
                subprocess.run(build_command, cwd=ROOT, check=True)
            except subprocess.CalledProcessError as error:
                print(f"Error durante la build debug: {error}")
                return error.returncode or 1

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

    if args.exclude_orphan_ids:
        print("Modo debug: se excluyeron IDs compuestos solo por espacios.")
    if args.debug:
        print("Modo debug: se aplicó el marcador DEBUGING.")
    print(f"¡Empaquetado exitoso! Archivo generado en: {output_release}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
