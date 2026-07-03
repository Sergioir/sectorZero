"""
disco.py
=========
Motor principal de SectorZero: lectura e interpretación de la
estructura de un disco — tabla de particiones, sector de arranque,
estado del MBR/GPT.

Todo es SOLO LECTURA aquí. Este módulo nunca modifica nada.
Las operaciones de escritura están en operaciones.py.

Herramientas usadas:
  - parted -m -s <disco> unit B print free  → tabla de particiones
  - dd if=<disco> bs=512 count=1 | xxd      → leer MBR raw
  - gdisk -l <disco>                         → info GPT detallada
  - fdisk -l <disco>                         → alternativa a parted
"""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass, field, asdict
from typing import Optional

from sectorzero.core.wsl_utils import (
    wsl_disponible,
    comando_disponible_en_wsl,
    dispositivo_visible_en_wsl,
    ejecutar_en_wsl,
)


# ------------------------------------------------------------------
# Estructuras de datos
# ------------------------------------------------------------------

@dataclass
class InfoDisco:
    ruta: str
    tamaño_bytes: int
    transport: str        # usb, scsi, ata, nvme...
    sector_logico: int    # bytes (normalmente 512)
    sector_fisico: int    # bytes (512 o 4096 en discos avanzados)
    tipo_tabla: str       # msdos (MBR), gpt, loop, unknown
    modelo: str

    @property
    def tamaño_gb(self) -> float:
        return self.tamaño_bytes / 1e9

    @property
    def tipo_tabla_legible(self) -> str:
        m = {"msdos": "MBR (DOS)", "gpt": "GPT", "loop": "Loop",
             "unknown": "Desconocido", "": "Sin tabla detectada"}
        return m.get(self.tipo_tabla, self.tipo_tabla.upper())

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Particion:
    numero: int
    inicio_bytes: int
    fin_bytes: int
    tamaño_bytes: int
    filesystem: str     # exfat, ntfs, fat32, ext4, unknown, free...
    nombre: str         # nombre GPT o vacío en MBR
    flags: str          # boot, esp, lba...
    es_libre: bool = False  # True si es espacio no asignado

    @property
    def tamaño_gb(self) -> float:
        return self.tamaño_bytes / 1e9

    @property
    def inicio_mb(self) -> float:
        return self.inicio_bytes / 1e6

    @property
    def fin_mb(self) -> float:
        return self.fin_bytes / 1e6

    @property
    def porcentaje_inicio(self) -> float:
        """Para la barra visual — necesita el tamaño total del disco."""
        return 0.0  # se calcula en la GUI con disco.tamaño_bytes

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class EstadoMBR:
    """Estado del Master Boot Record (primeros 512 bytes del disco)."""
    firma_valida: bool           # 0x55AA en offset 510-511
    tiene_codigo_arranque: bool  # los primeros 446 bytes no son ceros
    firma_bytes: str             # "55AA" o lo que haya
    codigo_arranque_bytes: int   # cuántos bytes no son cero en la zona de código

    @property
    def descripcion(self) -> str:
        if not self.firma_valida:
            return f"Firma inválida: {self.firma_bytes} (esperado 55AA)"
        if not self.tiene_codigo_arranque:
            return "Firma válida pero sin código de arranque (disco no arrancable)"
        return "MBR válido — firma 55AA presente y código de arranque activo"

    @property
    def estado_visual(self) -> str:
        if not self.firma_valida:
            return "error"
        if not self.tiene_codigo_arranque:
            return "aviso"
        return "ok"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ResultadoLecturaDisco:
    """Resultado completo del análisis de un disco."""
    ejecucion_correcta: bool
    error: Optional[str] = None
    disco: Optional[InfoDisco] = None
    particiones: list[Particion] = field(default_factory=list)
    espacio_libre_bytes: int = 0
    estado_mbr: Optional[EstadoMBR] = None
    salida_parted: str = ""

    @property
    def tiene_tabla(self) -> bool:
        return (self.disco is not None and
                self.disco.tipo_tabla not in ("unknown", "", "loop"))

    @property
    def particiones_reales(self) -> list[Particion]:
        return [p for p in self.particiones if not p.es_libre]

    @property
    def espacios_libres(self) -> list[Particion]:
        return [p for p in self.particiones if p.es_libre]

    def to_dict(self) -> dict:
        return {
            'ejecucion_correcta': self.ejecucion_correcta,
            'error': self.error,
            'disco': self.disco.to_dict() if self.disco else None,
            'particiones': [p.to_dict() for p in self.particiones],
            'espacio_libre_bytes': self.espacio_libre_bytes,
            'estado_mbr': self.estado_mbr.to_dict() if self.estado_mbr else None,
        }


# ------------------------------------------------------------------
# Parser de parted --machine
# ------------------------------------------------------------------

def _parsear_parted_machine(salida: str) -> tuple[Optional[InfoDisco], list[Particion], int]:
    """Parsea 'parted -m -s /dev/X unit B print free'.
    Devuelve (InfoDisco, [Particion], espacio_libre_bytes)."""

    disco = None
    particiones = []
    espacio_libre = 0

    for linea in salida.splitlines():
        linea = linea.strip().rstrip(';')
        if not linea or linea == 'BYT':
            continue
        campos = linea.split(':')
        if not campos:
            continue

        # Línea de disco
        if campos[0].startswith('/dev/') or '\\\\' in campos[0] or campos[0].startswith('\\\\.\\'):
            try:
                disco = InfoDisco(
                    ruta=campos[0],
                    tamaño_bytes=int(campos[1].rstrip('B')),
                    transport=campos[2] if len(campos) > 2 else '',
                    sector_logico=int(campos[3]) if len(campos) > 3 and campos[3].isdigit() else 512,
                    sector_fisico=int(campos[4]) if len(campos) > 4 and campos[4].isdigit() else 512,
                    tipo_tabla=campos[5] if len(campos) > 5 else 'unknown',
                    modelo=campos[6] if len(campos) > 6 else '',
                )
            except (ValueError, IndexError):
                pass
            continue

        # Espacio libre
        if len(campos) >= 5 and campos[4] == 'free':
            try:
                libre = int(campos[3].rstrip('B'))
                espacio_libre += libre
                particiones.append(Particion(
                    numero=0,
                    inicio_bytes=int(campos[1].rstrip('B')),
                    fin_bytes=int(campos[2].rstrip('B')),
                    tamaño_bytes=libre,
                    filesystem='libre',
                    nombre='',
                    flags='',
                    es_libre=True,
                ))
            except (ValueError, IndexError):
                pass
            continue

        # Partición
        if campos[0].isdigit():
            try:
                particiones.append(Particion(
                    numero=int(campos[0]),
                    inicio_bytes=int(campos[1].rstrip('B')),
                    fin_bytes=int(campos[2].rstrip('B')),
                    tamaño_bytes=int(campos[3].rstrip('B')),
                    filesystem=campos[4] if len(campos) > 4 else '',
                    nombre=campos[5] if len(campos) > 5 else '',
                    flags=campos[6] if len(campos) > 6 else '',
                    es_libre=False,
                ))
            except (ValueError, IndexError):
                pass

    # Ordenar por inicio
    particiones.sort(key=lambda p: p.inicio_bytes)
    return disco, particiones, espacio_libre


# ------------------------------------------------------------------
# Funciones principales
# ------------------------------------------------------------------

def leer_disco(
    ruta_disco_wsl: str,
    distro: Optional[str] = None,
    timeout: int = 30,
) -> ResultadoLecturaDisco:
    """
    Lee la tabla de particiones y estado del MBR de un disco.
    SOLO LECTURA — no modifica nada.

    Lanza dos comandos en WSL:
      1. parted -m -s <disco> unit B print free
      2. dd if=<disco> bs=512 count=1 2>/dev/null | xxd
    """
    if not wsl_disponible():
        return ResultadoLecturaDisco(
            ejecucion_correcta=False,
            error="wsl.exe no encontrado.",
        )

    visible, msg = dispositivo_visible_en_wsl(ruta_disco_wsl, distro)
    if not visible:
        return ResultadoLecturaDisco(ejecucion_correcta=False, error=msg)

    # 1. Tabla de particiones con parted
    parted_ok, _ = comando_disponible_en_wsl("parted", distro)
    salida_parted = ""
    disco = None
    particiones = []
    espacio_libre = 0

    if parted_ok:
        try:
            proc = ejecutar_en_wsl(
                ["parted", "-m", "-s", ruta_disco_wsl, "unit", "B", "print", "free"],
                distro=distro, timeout=timeout,
            )
            salida_parted = proc.stdout + proc.stderr
            disco, particiones, espacio_libre = _parsear_parted_machine(salida_parted)
        except Exception as e:
            salida_parted = str(e)
    else:
        # Fallback: fdisk -l
        try:
            proc = ejecutar_en_wsl(
                ["fdisk", "-l", ruta_disco_wsl],
                distro=distro, timeout=timeout,
            )
            salida_parted = proc.stdout + proc.stderr
            disco, particiones, espacio_libre = _parsear_fdisk(salida_parted, ruta_disco_wsl)
        except Exception as e:
            salida_parted = str(e)

    # 2. Leer MBR (primeros 512 bytes)
    estado_mbr = None
    try:
        proc_mbr = ejecutar_en_wsl(
            ["dd", f"if={ruta_disco_wsl}", "bs=512", "count=1"],
            distro=distro, timeout=15,
        )
        # La salida de dd va a stderr, los datos a stdout (binario)
        # Como capturamos como texto, usamos xxd para convertir
        proc_xxd = ejecutar_en_wsl(
            ["bash", "-c", f"dd if={ruta_disco_wsl} bs=512 count=1 2>/dev/null | xxd"],
            distro=distro, timeout=15,
        )
        estado_mbr = _analizar_mbr_xxd(proc_xxd.stdout)
    except Exception:
        pass

    if disco is None and not particiones:
        return ResultadoLecturaDisco(
            ejecucion_correcta=False,
            error=f"No se pudo leer la tabla de particiones. {salida_parted[:200]}",
        )

    return ResultadoLecturaDisco(
        ejecucion_correcta=True,
        disco=disco,
        particiones=particiones,
        espacio_libre_bytes=espacio_libre,
        estado_mbr=estado_mbr,
        salida_parted=salida_parted,
    )


def _analizar_mbr_xxd(salida_xxd: str) -> EstadoMBR:
    """Analiza la salida de xxd del primer sector para determinar el estado del MBR."""
    # Extraer bytes en hex de la salida de xxd
    bytes_hex = []
    for linea in salida_xxd.splitlines():
        # Formato xxd: "00000000: 33c0 8ed0 bc00 7cfb ..."
        m = re.match(r'^[0-9a-f]+:\s+((?:[0-9a-f]{4}\s*)+)', linea)
        if m:
            grupo = m.group(1).replace(' ', '')
            for i in range(0, len(grupo), 2):
                if i + 1 < len(grupo):
                    bytes_hex.append(int(grupo[i:i+2], 16))

    if len(bytes_hex) < 512:
        return EstadoMBR(
            firma_valida=False,
            tiene_codigo_arranque=False,
            firma_bytes="??",
            codigo_arranque_bytes=0,
        )

    # Firma en offset 510-511
    firma = f"{bytes_hex[510]:02X}{bytes_hex[511]:02X}"
    firma_valida = bytes_hex[510] == 0x55 and bytes_hex[511] == 0xAA

    # Código de arranque: primeros 446 bytes (zona de bootloader)
    zona_codigo = bytes_hex[:446]
    bytes_no_cero = sum(1 for b in zona_codigo if b != 0)

    return EstadoMBR(
        firma_valida=firma_valida,
        tiene_codigo_arranque=bytes_no_cero > 10,
        firma_bytes=firma,
        codigo_arranque_bytes=bytes_no_cero,
    )


def _parsear_fdisk(salida: str, ruta: str) -> tuple[Optional[InfoDisco], list[Particion], int]:
    """Fallback: parsear salida de fdisk -l cuando parted no está disponible."""
    disco = None
    particiones = []

    # Buscar info del disco
    m_disco = re.search(
        r'Disk ' + re.escape(ruta) + r':\s+[\d.]+\s+\w+,\s+(\d+)\s+bytes',
        salida
    )
    if m_disco:
        disco = InfoDisco(
            ruta=ruta,
            tamaño_bytes=int(m_disco.group(1)),
            transport='',
            sector_logico=512,
            sector_fisico=512,
            tipo_tabla='msdos',
            modelo='',
        )

    # Buscar particiones
    for linea in salida.splitlines():
        m = re.match(
            r'(/dev/\S+)\s+[\*\s]\s+(\d+)\s+(\d+)\s+(\d+)\s+\S+\s+(.*)',
            linea
        )
        if m:
            try:
                particiones.append(Particion(
                    numero=len(particiones) + 1,
                    inicio_bytes=int(m.group(2)) * 512,
                    fin_bytes=int(m.group(3)) * 512,
                    tamaño_bytes=int(m.group(4)) * 512,
                    filesystem=m.group(5).strip().lower()[:10],
                    nombre='',
                    flags='',
                    es_libre=False,
                ))
            except ValueError:
                pass

    return disco, particiones, 0


def listar_discos_wsl(
    distro: Optional[str] = None,
    timeout: int = 15,
) -> list[dict]:
    """Lista los discos disponibles dentro de WSL con info de tamaño y tipo.
    Filtra los discos virtuales de WSL (sda-sdd normalmente) mostrando
    solo los que parecen discos físicos reales (removibles o >10GB externos).
    Devuelve lista de dicts: {ruta, tamaño, removible, modelo}"""
    try:
        proc = ejecutar_en_wsl(
            ["lsblk", "-d", "-o", "NAME,SIZE,RM,TYPE,TRAN,MODEL", "-n", "--bytes"],
            distro=distro, timeout=timeout,
        )
        discos = []
        for linea in proc.stdout.splitlines():
            partes = linea.split()
            if len(partes) < 4:
                continue
            nombre = partes[0]
            tipo = partes[3] if len(partes) > 3 else ""
            if tipo != "disk":
                continue
            try:
                tamaño_bytes = int(partes[1])
            except ValueError:
                continue
            removible = partes[2] == "1"
            transport = partes[4] if len(partes) > 4 else ""
            modelo = " ".join(partes[5:]) if len(partes) > 5 else ""
            tamaño_gb = tamaño_bytes / 1e9

            # Filtrar discos virtuales de WSL:
            # - Los discos de WSL son virtual/loop y tienen transporte vacío
            # - Los discos físicos USB tienen transport="usb" o son removibles
            # - Los discos SATA/NVMe reales tienen transport="sata","nvme","ata"
            es_virtual_wsl = (
                not removible
                and transport in ("", "virtual")
                and tamaño_gb < 2000  # discos virtuales de WSL raramente superan 2TB
                and not modelo
            )

            discos.append({
                "ruta": f"/dev/{nombre}",
                "tamaño_bytes": tamaño_bytes,
                "tamaño_gb": tamaño_gb,
                "removible": removible,
                "transport": transport,
                "modelo": modelo or "Desconocido",
                "es_virtual_wsl": es_virtual_wsl,
                "label": _formatear_label_disco(nombre, tamaño_gb, removible, transport, modelo),
            })
        return discos
    except Exception:
        return []


def _formatear_label_disco(nombre: str, gb: float, rm: bool,
                             transport: str, modelo: str) -> str:
    """Etiqueta legible para el selector de disco."""
    tipo = ""
    if transport == "usb" or rm:
        tipo = "USB"
    elif transport in ("sata", "ata"):
        tipo = "SATA"
    elif transport == "nvme":
        tipo = "NVMe"
    elif not transport:
        tipo = "Virtual"

    modelo_corto = modelo[:20] if modelo else "Desconocido"
    return f"/dev/{nombre}  {gb:.1f}GB  {tipo}  {modelo_corto}"
