#!/usr/bin/env python3

import os
import subprocess
import sys
from pathlib import Path


def main():
    import platform
    system = platform.system().lower()
    
    bin_path = None
    if "linux" in system:
        bin_path = Path("tools/big4f/bin/linux/big4f")
    elif "windows" in system:
        bin_path = Path("tools/big4f/bin/windows/big4f.exe")
    elif "darwin" in system:
        bin_path = Path("tools/big4f/bin/macos/big4f")

    if not bin_path or not bin_path.exists():
        print(f"Error: No se encontró el binario de big4f para el sistema '{system}' en {bin_path}")
        sys.exit(1)

    bin_path = bin_path.resolve()
    source_dir = Path("translations/spanish").resolve()
    output_release = Path("releases/spanishpatch202.big").resolve()
    output_release.parent.mkdir(parents=True, exist_ok=True)

    print(f"Empaquetando {source_dir} usando {bin_path}...")
    
    original_cwd = os.getcwd()
    try:
        os.chdir(source_dir)
        subprocess.run([str(bin_path), "f", ".", str(output_release)], check=True)
        print(f"¡Empaquetado exitoso! Archivo generado en: {output_release}")
    except subprocess.CalledProcessError as e:
        print(f"Error durante el empaquetado con big4f: {e}")
        sys.exit(1)
    finally:
        os.chdir(original_cwd)


if __name__ == "__main__":
    main()
