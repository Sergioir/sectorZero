"""
wsl_utils.py
============
Utilidades compartidas para interactuar con WSL2 desde Windows.
Extraido de imagen.py porque tanto el modulo de imagen como el de
reparacion de sistemas de archivos necesitan las mismas comprobaciones
basicas (WSL disponible, dispositivo visible, traduccion de rutas).

Mantener esto en un solo sitio evita que la logica de "como hablamos
con WSL" diverja entre modulos -- un bug arreglado aqui se arregla
para todos los que lo usen.
"""

from __future__ import annotations

import platform
import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional

# En Windows con PyInstaller (console=False), cada subprocess.run/Popen
# hereda la consola del proceso padre -- que no existe -- y abre una
# ventana negra momentanea. CREATE_NO_WINDOW suprime ese comportamiento.
# En Linux el flag no existe, asi que se define a 0 (sin efecto).
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def wsl_disponible() -> bool:
    return shutil.which("wsl") is not None or shutil.which("wsl.exe") is not None


def comando_disponible_en_wsl(nombre_comando: str, distro: Optional[str] = None, timeout: int = 15) -> tuple[bool, str]:
    comando = ["wsl"]
    if distro:
        comando += ["-d", distro]
    comando += ["-u", "root", "--", "which", nombre_comando]
    try:
        proc = subprocess.run(comando, capture_output=True, text=True, encoding="utf-8", errors="replace",
                               timeout=timeout, creationflags=_NO_WINDOW)
    except Exception as e:
        return False, f"No se pudo consultar WSL: {e}"

    if proc.returncode != 0 or not proc.stdout.strip():
        return False, f"'{nombre_comando}' no esta instalado en la distro WSL."
    return True, proc.stdout.strip()


def dispositivo_visible_en_wsl(ruta_dispositivo_wsl: str, distro: Optional[str] = None, timeout: int = 15) -> tuple[bool, str]:
    comando = ["wsl"]
    if distro:
        comando += ["-d", distro]
    comando += ["-u", "root", "--", "test", "-e", ruta_dispositivo_wsl]
    try:
        proc = subprocess.run(comando, capture_output=True, text=True, encoding="utf-8", errors="replace",
                               timeout=timeout, creationflags=_NO_WINDOW)
    except Exception as e:
        return False, f"No se pudo verificar el dispositivo en WSL: {e}"

    if proc.returncode != 0:
        return False, (
            f"El dispositivo '{ruta_dispositivo_wsl}' no es visible dentro de WSL. "
            "Esto es normal si todavia no se ha expuesto el disco a la VM de WSL. "
            "Para discos USB: 'usbipd bind --busid <ID>' seguido de "
            "'usbipd attach --wsl --busid <ID>' (requiere una sesion WSL activa). "
            "Para discos internos SATA/NVMe: 'wsl --mount' (no soportado en todas "
            "las versiones de WSL). Comprobar con 'wsl -- lsblk' que el disco aparece "
            "antes de reintentar."
        )
    return True, "Dispositivo visible."


def ruta_windows_a_wsl(ruta_windows: str) -> str:
    m = re.match(r"^([A-Za-z]):\\(.*)$", ruta_windows)
    if not m:
        return ruta_windows.replace("\\", "/")
    letra, resto = m.groups()
    resto_unix = resto.replace("\\", "/")
    return f"/mnt/{letra.lower()}/{resto_unix}"


def ejecutar_en_wsl(
    argumentos: list[str],
    distro: Optional[str] = None,
    timeout: Optional[int] = None,
    usar_sudo: bool = False,
    usar_root: bool = True,
) -> subprocess.CompletedProcess:
    """Ejecuta un comando dentro de WSL con la ventana suprimida.

    usar_root=True (default): usa '-u root' para ejecutar como root sin
        pedir contraseña — el método correcto para operaciones que necesitan
        privilegios. Ignora usar_sudo si usar_root=True.
    usar_sudo=True: usa 'sudo' delante del comando. Solo útil si el usuario
        tiene sudo configurado sin contraseña. En Kali WSL por defecto pide
        contraseña, así que usar_root=True es siempre preferible.
    """
    comando = ["wsl"]
    if distro:
        comando += ["-d", distro]
    if usar_root:
        comando += ["-u", "root"]
    comando += ["--"]
    if usar_sudo and not usar_root:
        comando += ["sudo"]
    comando += argumentos
    return subprocess.run(comando, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=timeout, creationflags=_NO_WINDOW)
