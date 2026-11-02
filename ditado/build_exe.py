"""Gera o executável do Ditado com PyInstaller.

Uso (de dentro da pasta ditado, com as dependências instaladas):
    python build_exe.py

Resultado: dist/Ditado/Ditado.exe (Windows) ou dist/Ditado/Ditado.
Copie a pasta dist/Ditado inteira; o executável precisa dos arquivos ao lado.
"""

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def make_icon() -> Path:
    from ditado import make_icon_image

    ico = HERE / "ditado.ico"
    img = make_icon_image("pronto").resize((256, 256))
    img.save(ico, sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    return ico


# Bibliotecas com arquivos de dados/DLLs que o PyInstaller não acha sozinho.
COLLECT_ALL = ["faster_whisper", "ctranslate2", "onnxruntime", "tokenizers", "_sounddevice_data"]


def collect_args() -> list:
    import importlib.util

    args = []
    for pkg in COLLECT_ALL:
        if importlib.util.find_spec(pkg) is not None:  # _sounddevice_data só existe no Windows/Mac
            args += ["--collect-all", pkg]
    return args


def main() -> None:
    ico = make_icon()
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean",
        "--name", "Ditado",
        "--windowed",            # sem janela preta de console
        "--onedir",              # abre bem mais rápido que --onefile
        "--icon", str(ico),
        *collect_args(),
        "--collect-submodules", "pynput",
        "--collect-submodules", "pystray",
        "--distpath", str(HERE / "dist"),
        "--workpath", str(HERE / "build"),
        "--specpath", str(HERE / "build"),
        str(HERE / "ditado.py"),
    ]
    print(" ".join(cmd))
    subprocess.check_call(cmd, cwd=HERE)
    exe = "Ditado.exe" if sys.platform.startswith("win") else "Ditado"
    print(f"\nPronto! Executável em: {HERE / 'dist' / 'Ditado' / exe}")


if __name__ == "__main__":
    main()
