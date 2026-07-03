"""
usbipd_utils.py
================
Utilidades para listar dispositivos USB con usbipd, cruzar con lsblk
para obtener tamaños, y construir la tabla de selección de la GUI.

El problema que resuelve: usbipd list muestra BUSID y nombre genérico
("Dispositivo de almacenamiento USB") pero no el tamaño ni el modelo
real. lsblk dentro de WSL sí tiene el tamaño. Cruzando los dos:
  - usbipd list  → BUSID, VID:PID, nombre, estado (Shared/Not shared)
  - wsl lsblk    → /dev/sdX, tamaño, si es removible

El cruce se hace por orden de aparición: los discos removibles en WSL
corresponden a los dispositivos "Shared" de usbipd en el mismo orden
en que se hicieron attach. Esto es una heurística razonable pero no
garantizada — se muestra claramente al usuario para que confirme.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from typing import Optional

from sectorzero.core.wsl_utils import _NO_WINDOW, ejecutar_en_wsl


@dataclass
class DispositivoUSB:
    """Un dispositivo USB tal como lo ve usbipd."""
    busid: str
    vidpid: str
    nombre: str
    estado: str                    # "Not shared" | "Shared" | "Attached"
    es_almacenamiento: bool = False

    @property
    def compartido(self) -> bool:
        """True si usbipd lo tiene registrado (bind hecho), sea o no adjunto a WSL."""
        return self.estado.lower() in ("shared", "attached")

    @property
    def adjunto_a_wsl(self) -> bool:
        """True si ya está dentro de WSL como /dev/sdX."""
        return self.estado.lower() == "attached"

    @property
    def necesita_attach(self) -> bool:
        """True si está compartido (bind hecho) pero todavía no adjunto a WSL."""
        return self.estado.lower() == "shared"

    @property
    def estado_legible(self) -> str:
        if self.estado.lower() == "not shared":
            return "No registrado"
        if self.estado.lower() == "shared":
            return "Listo — pulsa Conectar"
        if self.estado.lower() == "attached":
            return "En WSL ✓"
        return self.estado


@dataclass
class DiscoWSL:
    """Un disco tal como lo ve lsblk dentro de WSL."""
    nombre: str          # /dev/sde
    size: str            # "234.4G"
    removible: bool
    particiones: list[str] = field(default_factory=list)  # ["/dev/sde1"]


@dataclass
class ResultadoListaUSB:
    ejecucion_correcta: bool
    error: Optional[str] = None
    dispositivos_usbipd: list[DispositivoUSB] = field(default_factory=list)
    discos_wsl: list[DiscoWSL] = field(default_factory=list)
    cruces: list[tuple[DispositivoUSB, DiscoWSL]] = field(default_factory=list)
    info_windows: dict = field(default_factory=dict)  # Get-Disk: número → {FriendlyName, Size}


def _obtener_info_discos_windows() -> dict[str, dict]:
    """Obtiene modelo de discos USB desde PowerShell via Get-PnpDevice,
    indexado por VID:PID en minúsculas — que coincide exactamente con
    lo que muestra usbipd list, permitiendo un cruce fiable."""
    try:
        import subprocess, json
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             "Get-PnpDevice -Class DiskDrive | "
             "Where-Object {$_.DeviceID -like '*USB*'} | "
             "Select-Object FriendlyName, DeviceID | ConvertTo-Json"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10,
            creationflags=_NO_WINDOW,
        )
        if proc.returncode != 0 or not proc.stdout.strip():
            return {}
        datos = json.loads(proc.stdout)
        if isinstance(datos, dict):
            datos = [datos]
        resultado = {}
        for d in datos:
            if not d:
                continue
            device_id = (d.get("DeviceID") or "").upper()
            # Extraer VID:PID del DeviceID: USB\VID_346D&PID_5678\...
            m = re.search(r'VID_([0-9A-F]{4})&PID_([0-9A-F]{4})', device_id)
            if m:
                vidpid = f"{m.group(1).lower()}:{m.group(2).lower()}"
                resultado[vidpid] = {
                    "FriendlyName": d.get("FriendlyName", ""),
                    "DeviceID": device_id,
                }
        return resultado
    except Exception:
        return {}


def _parsear_usbipd_list(salida: str) -> list[DispositivoUSB]:
    """Parsea la salida de 'usbipd list'."""
    dispositivos = []
    en_connected = False
    for linea in salida.splitlines():
        linea_strip = linea.strip()
        if linea_strip.startswith("Connected:"):
            en_connected = True
            continue
        if linea_strip.startswith("Persisted:") or linea_strip.startswith("GUID"):
            en_connected = False
            continue
        if not en_connected:
            continue
        # Cabecera
        if linea_strip.startswith("BUSID"):
            continue

        # Formato: BUSID  VID:PID  DEVICE NAME...   STATE
        m = re.match(
            r'^(\d+-\d+)\s+([0-9a-fA-F]{4}:[0-9a-fA-F]{4})\s+(.+?)\s{2,}(Not shared|Shared|Attached)',
            linea_strip, re.IGNORECASE
        )
        if m:
            busid = m.group(1)
            vidpid = m.group(2)
            nombre = m.group(3).strip()
            estado = m.group(4).strip()
            es_alm = any(p in nombre.lower() for p in
                         ("almacenamiento", "storage", "disk", "mass storage", "flash"))
            dispositivos.append(DispositivoUSB(
                busid=busid, vidpid=vidpid, nombre=nombre,
                estado=estado, es_almacenamiento=es_alm,
            ))
    return dispositivos


def _parsear_lsblk(salida: str) -> list[DiscoWSL]:
    """Parsea la salida de 'lsblk' dentro de WSL."""
    discos: dict[str, DiscoWSL] = {}
    for linea in salida.splitlines():
        linea = linea.strip().lstrip("└─├─")
        # Disco: sde  8:64  1  234.4G  0  disk
        m_disco = re.match(r'^(sd[a-z])\s+\S+\s+(\d)\s+(\S+)\s+\d\s+disk', linea)
        if m_disco:
            nombre = f"/dev/{m_disco.group(1)}"
            removible = m_disco.group(2) == "1"
            size = m_disco.group(3)
            discos[nombre] = DiscoWSL(nombre=nombre, size=size, removible=removible)
            continue
        # Partición: sde1  8:65  1  234.4G  0  part
        m_part = re.match(r'^(sd[a-z]\d+)\s+\S+\s+\d\s+(\S+)\s+\d\s+part', linea)
        if m_part:
            nombre_part = f"/dev/{m_part.group(1)}"
            disco_padre = f"/dev/{m_part.group(1)[:-1]}"  # quitar dígito final
            if disco_padre in discos:
                discos[disco_padre].particiones.append(nombre_part)
    return list(discos.values())


def listar_usb_para_gui(distro: Optional[str] = None) -> ResultadoListaUSB:
    """
    Obtiene la lista de dispositivos USB de usbipd y los discos de WSL,
    y construye el cruce para mostrar en la GUI.
    """
    # 1. usbipd list (comando Windows, no WSL)
    try:
        proc_usbipd = subprocess.run(
            ["usbipd", "list"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15,
            creationflags=_NO_WINDOW,
        )
        if proc_usbipd.returncode != 0 and not proc_usbipd.stdout:
            return ResultadoListaUSB(
                ejecucion_correcta=False,
                error="usbipd no está instalado o no responde. Instálalo desde la pantalla de configuración.",
            )
        dispositivos = _parsear_usbipd_list(proc_usbipd.stdout)
    except FileNotFoundError:
        return ResultadoListaUSB(
            ejecucion_correcta=False,
            error="usbipd no encontrado. Instálalo desde la pantalla de configuración inicial.",
        )
    except Exception as e:
        return ResultadoListaUSB(ejecucion_correcta=False, error=str(e))

    # 2. lsblk dentro de WSL
    try:
        proc_lsblk = ejecutar_en_wsl(["lsblk"], distro=distro, timeout=10)
        discos_wsl = _parsear_lsblk(proc_lsblk.stdout)
    except Exception:
        discos_wsl = []

    # 3. Info de Get-Disk para nombres reales y tamaños
    info_windows = _obtener_info_discos_windows()

    # 4. Cruce: solo los adjuntos a WSL tienen disco visible en lsblk
    adjuntos = [d for d in dispositivos if d.es_almacenamiento and d.adjunto_a_wsl]
    removibles = [d for d in discos_wsl if d.removible]
    cruces = list(zip(adjuntos, removibles))

    return ResultadoListaUSB(
        ejecucion_correcta=True,
        dispositivos_usbipd=dispositivos,
        discos_wsl=discos_wsl,
        cruces=cruces,
        info_windows=info_windows,
    )


def _desmontar_de_windows(vidpid: str) -> None:
    """Intenta desmontar el disco de Windows antes de pasarlo a WSL.
    Usa PowerShell para encontrar el volumen por VID:PID y expulsarlo."""
    try:
        import subprocess
        # Encontrar la letra de unidad del dispositivo por VID:PID
        vid, pid = vidpid.upper().split(":")
        script = (
            f"$dev = Get-PnpDevice -Class DiskDrive | "
            f"Where-Object {{$_.DeviceID -like '*VID_{vid}*PID_{pid}*'}} | "
            f"Select-Object -First 1; "
            f"if ($dev) {{"
            f"  $disk = Get-Disk | Where-Object {{$_.SerialNumber -ne $null}} | "
            f"  Get-Partition | Get-Volume | Select-Object -First 1; "
            f"  if ($disk) {{ $disk | Dismount-Volume -Confirm:$false }}"
            f"}}"
        )
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15,
            creationflags=_NO_WINDOW,
        )
    except Exception:
        pass  # no crítico — el attach intentará igualmente


def bind_y_attach(busid: str, distro: Optional[str] = None,
                   vidpid: Optional[str] = None) -> tuple[bool, str]:
    """Ejecuta usbipd bind + attach para un BUSID dado.
    Si falla por 'device busy', intenta desmontar de Windows primero."""
    try:
        # bind
        subprocess.run(
            ["usbipd", "bind", "--busid", busid],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15,
            creationflags=_NO_WINDOW,
        )

        def _attach() -> tuple[int, str]:
            args = (["usbipd", "attach", "--wsl", "--busid", busid]
                    + ([f"--distribution={distro}"] if distro else []))
            p = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace",
                                timeout=30, creationflags=_NO_WINDOW)
            return p.returncode, (p.stdout + p.stderr).strip()

        codigo, salida = _attach()
        if codigo == 0:
            return True, salida

        # Si falla por busy: desmontar de Windows y reintentar
        if "busy" in salida.lower() or "exported" in salida.lower() or "used by windows" in salida.lower():
            if vidpid:
                _desmontar_de_windows(vidpid)
            # También hacer detach por si acaso
            subprocess.run(
                ["usbipd", "detach", "--busid", busid],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15,
                creationflags=_NO_WINDOW,
            )
            import time
            time.sleep(2)
            codigo2, salida2 = _attach()
            if codigo2 == 0:
                return True, salida2
            return False, f"Sigue bloqueado tras desmontar. {salida2}\nSugerencia: expulsa el disco desde la bandeja del sistema (icono USB en la esquina inferior derecha) y vuelve a intentarlo."

        return False, salida
    except Exception as e:
        return False, str(e)


def detach(busid: str) -> tuple[bool, str]:
    """Desconecta un dispositivo USB de WSL."""
    try:
        proc = subprocess.run(
            ["usbipd", "detach", "--busid", busid],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15,
            creationflags=_NO_WINDOW,
        )
        return proc.returncode == 0, (proc.stdout + proc.stderr).strip()
    except Exception as e:
        return False, str(e)
