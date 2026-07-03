"""
instalacion.py — SectorZero
=============================
Pasos de instalación de dependencias. Mismo patrón que Disk Surgeon
pero solo las herramientas que SectorZero necesita.
"""

from __future__ import annotations

import platform
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class TipoEjecucion(Enum):
    POWERSHELL_ADMIN  = "powershell_admin"
    POWERSHELL_NORMAL = "powershell_normal"
    WSL               = "wsl"


@dataclass
class PasoInstalacion:
    id: str
    nombre: str
    descripcion_corta: str
    descripcion_larga: str
    comando: str
    tipo_ejecucion: TipoEjecucion
    verificar: Callable[[], bool]
    requiere_reinicio: bool = False
    opcional: bool = False
    solo_windows: bool = True
    advertencia: Optional[str] = None


# ------------------------------------------------------------------
# Funciones de verificación
# ------------------------------------------------------------------

def _wsl_instalado() -> bool:
    if platform.system() != "Windows":
        return True
    if not shutil.which("wsl"):
        return False
    try:
        proc = subprocess.run(["wsl", "--list", "--quiet"],
                               capture_output=True, text=True, timeout=10,
                               creationflags=_NO_WINDOW)
        return proc.returncode == 0
    except Exception:
        return False


def _distro_instalada(nombre: str = "kali-linux") -> bool:
    if platform.system() != "Windows":
        return True
    try:
        proc = subprocess.run(["wsl", "--list", "--quiet"],
                               capture_output=True, timeout=10,
                               creationflags=_NO_WINDOW)
        try:
            salida = proc.stdout.decode("utf-16-le", errors="ignore")
        except Exception:
            salida = proc.stdout.decode("utf-8", errors="ignore")
        return nombre.lower() in salida.lower()
    except Exception:
        return False


def _cmd_en_wsl(cmd: str) -> bool:
    if platform.system() != "Windows":
        return bool(shutil.which(cmd))
    try:
        proc = subprocess.run(
            ["wsl", "-u", "root", "--", "which", cmd],
            capture_output=True, text=True, timeout=15,
            creationflags=_NO_WINDOW,
        )
        return proc.returncode == 0 and bool(proc.stdout.strip())
    except Exception:
        return False


# ------------------------------------------------------------------
# Pasos de instalación
# ------------------------------------------------------------------

PASOS: list[PasoInstalacion] = [

    PasoInstalacion(
        id="wsl2",
        nombre="WSL2 (Subsistema de Windows para Linux)",
        descripcion_corta="Necesario para ejecutar parted y las herramientas de disco",
        descripcion_larga=(
            "WSL2 es la capa de virtualización de Linux integrada en Windows 10/11. "
            "SectorZero la usa para ejecutar parted, fdisk y otras herramientas de "
            "gestión de particiones que no existen de forma nativa en Windows."
        ),
        comando="wsl --install",
        tipo_ejecucion=TipoEjecucion.POWERSHELL_ADMIN,
        verificar=_wsl_instalado,
        requiere_reinicio=True,
        advertencia="Requiere reiniciar Windows después de instalar.",
    ),

    PasoInstalacion(
        id="kali_linux",
        nombre="Kali Linux (distro WSL)",
        descripcion_corta="Distribución Linux con herramientas de sistema preinstaladas",
        descripcion_larga=(
            "Kali Linux es la distribución que SectorZero usa dentro de WSL. "
            "Incluye o permite instalar fácilmente parted, gdisk, fdisk y otras "
            "herramientas de gestión de particiones y discos."
        ),
        comando="wsl --install -d kali-linux",
        tipo_ejecucion=TipoEjecucion.POWERSHELL_ADMIN,
        verificar=lambda: _distro_instalada("kali-linux"),
    ),

    PasoInstalacion(
        id="parted",
        nombre="GNU parted",
        descripcion_corta="Gestión de tablas de particiones MBR y GPT",
        descripcion_larga=(
            "parted es la herramienta principal de SectorZero. Lee e interpreta "
            "tablas de particiones MBR y GPT, y permite crear, eliminar y modificar "
            "particiones de forma segura. SectorZero lo usa en modo no interactivo "
            "(-s) mostrando siempre el comando antes de ejecutarlo."
        ),
        comando="wsl -d kali-linux -u root -- apt install -y parted",
        tipo_ejecucion=TipoEjecucion.WSL,
        verificar=lambda: _cmd_en_wsl("parted"),
    ),

    PasoInstalacion(
        id="gdisk",
        nombre="gdisk (GPT fdisk)",
        descripcion_corta="Herramienta especializada en discos GPT",
        descripcion_larga=(
            "gdisk complementa a parted para discos GPT: puede recuperar tablas GPT "
            "dañadas, crear respaldos de la tabla GPT secundaria, y reparar "
            "inconsistencias entre la tabla GPT primaria y la secundaria. "
            "Especialmente útil cuando parted no puede leer el disco."
        ),
        comando="wsl -d kali-linux -u root -- apt install -y gdisk",
        tipo_ejecucion=TipoEjecucion.WSL,
        verificar=lambda: _cmd_en_wsl("gdisk"),
    ),
]


def verificar_todos() -> dict[str, bool]:
    sistema = platform.system()
    return {
        p.id: p.verificar()
        for p in PASOS
        if not (p.solo_windows and sistema != "Windows")
    }


def pasos_aplicables() -> list[PasoInstalacion]:
    sistema = platform.system()
    return [p for p in PASOS if not (p.solo_windows and sistema != "Windows")]
