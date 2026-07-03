"""
simulacion.py — SectorZero
============================
Simulación de operaciones sobre tablas de particiones.

Dado que parted 3.6 no tiene --pretend, calculamos en Python
cómo quedaría la tabla después de cada operación, sin tocar el disco.

La simulación es conservadora — si hay cualquier duda sobre el resultado,
lo indica claramente. No es perfecta (parted puede hacer ajustes de
alineación que no podemos predecir exactamente) pero es suficiente para
que el usuario vea qué va a pasar antes de confirmar.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from sectorzero.core.disco import Particion, ResultadoLecturaDisco, InfoDisco


@dataclass
class LineaSimulacion:
    """Una línea de la tabla simulada — puede ser partición real, libre, o nueva."""
    numero: Optional[int]       # None si es espacio libre
    inicio_bytes: int
    fin_bytes: int
    tamaño_bytes: int
    filesystem: str
    nombre: str
    flags: str
    estado: str = "igual"       # "igual" | "nueva" | "eliminada" | "modificada" | "libre"

    @property
    def tamaño_gb(self) -> float:
        return self.tamaño_bytes / 1e9

    @property
    def inicio_mb(self) -> float:
        return self.inicio_bytes / 1e6

    @property
    def fin_mb(self) -> float:
        return self.fin_bytes / 1e6


@dataclass
class ResultadoSimulacion:
    """Resultado de una simulación de operación."""
    posible: bool                          # ¿la operación es posible?
    motivo_imposible: Optional[str] = None # por qué no es posible
    advertencias: list[str] = field(default_factory=list)
    tabla_antes: list[LineaSimulacion] = field(default_factory=list)
    tabla_despues: list[LineaSimulacion] = field(default_factory=list)
    comando_parted: str = ""
    descripcion: str = ""

    def to_dict(self) -> dict:
        return {
            'posible': self.posible,
            'motivo_imposible': self.motivo_imposible,
            'advertencias': self.advertencias,
            'comando_parted': self.comando_parted,
            'descripcion': self.descripcion,
        }


def _tabla_a_lineas(resultado) -> list[LineaSimulacion]:
    """Convierte un ResultadoLecturaDisco en lista de LineaSimulacion."""
    lineas = []
    for p in resultado.particiones:
        lineas.append(LineaSimulacion(
            numero=p.numero if not p.es_libre else None,
            inicio_bytes=p.inicio_bytes,
            fin_bytes=p.fin_bytes,
            tamaño_bytes=p.tamaño_bytes,
            filesystem=p.filesystem,
            nombre=p.nombre,
            flags=p.flags,
            estado="libre" if p.es_libre else "igual",
        ))
    return sorted(lineas, key=lambda l: l.inicio_bytes)


def simular_crear_tabla(resultado_actual, tipo: str = "gpt") -> ResultadoSimulacion:
    """Simula crear una tabla de particiones nueva (borra todo)."""
    antes = _tabla_a_lineas(resultado_actual)
    disco = resultado_actual.disco

    # Marcar todas las particiones como "eliminadas"
    antes_marcado = []
    for l in antes:
        if l.estado != "libre":
            l.estado = "eliminada"
        antes_marcado.append(l)

    # Después: disco vacío con todo como espacio libre
    despues = [LineaSimulacion(
        numero=None,
        inicio_bytes=1048576,  # 1MB — offset estándar
        fin_bytes=disco.tamaño_bytes,
        tamaño_bytes=disco.tamaño_bytes - 1048576,
        filesystem="libre",
        nombre="",
        flags="",
        estado="libre",
    )]

    advertencias = []
    if any(l.estado == "eliminada" for l in antes_marcado):
        n = sum(1 for l in antes_marcado if l.estado == "eliminada")
        advertencias.append(
            f"Se eliminarán {n} partición(es) existente(s) y todos sus datos."
        )
    if tipo == "msdos":
        advertencias.append(
            "MBR (msdos) solo soporta discos hasta 2TB y máximo 4 particiones primarias."
        )

    return ResultadoSimulacion(
        posible=True,
        advertencias=advertencias,
        tabla_antes=antes_marcado,
        tabla_despues=despues,
        comando_parted=f"parted -s {disco.ruta} mklabel {tipo}",
        descripcion=f"Crear tabla {tipo.upper()} en {disco.ruta} — borra todo",
    )


def simular_crear_particion(
    resultado_actual,
    inicio_mb: float,
    fin_mb: float,
    filesystem: str,
    nombre: str = "",
) -> ResultadoSimulacion:
    """Simula crear una nueva partición."""
    disco = resultado_actual.disco
    inicio_bytes = int(inicio_mb * 1e6)
    fin_bytes = int(fin_mb * 1e6)
    tamaño_bytes = fin_bytes - inicio_bytes

    # Verificar que hay espacio libre en ese rango
    particiones_reales = resultado_actual.particiones_reales
    for p in particiones_reales:
        # ¿Solapamiento?
        if not (fin_bytes <= p.inicio_bytes or inicio_bytes >= p.fin_bytes):
            return ResultadoSimulacion(
                posible=False,
                motivo_imposible=(
                    f"El rango {inicio_mb:.0f}MB-{fin_mb:.0f}MB solapa con la "
                    f"partición #{p.numero} ({p.inicio_mb:.0f}MB-{p.fin_mb:.0f}MB)."
                ),
                comando_parted=(
                    f"parted -s {disco.ruta} unit MB mkpart primary "
                    f"{filesystem} {inicio_mb:.2f} {fin_mb:.2f}"
                ),
            )

    # Verificar tamaño mínimo
    if tamaño_bytes < 1048576:  # 1MB mínimo
        return ResultadoSimulacion(
            posible=False,
            motivo_imposible="La partición debe tener al menos 1MB.",
            comando_parted="",
        )

    # Calcular nuevo número de partición
    nums_existentes = [p.numero for p in particiones_reales]
    nuevo_num = max(nums_existentes) + 1 if nums_existentes else 1

    # Construir tabla resultante
    antes = _tabla_a_lineas(resultado_actual)
    nueva = LineaSimulacion(
        numero=nuevo_num,
        inicio_bytes=inicio_bytes,
        fin_bytes=fin_bytes,
        tamaño_bytes=tamaño_bytes,
        filesystem=filesystem,
        nombre=nombre,
        flags="",
        estado="nueva",
    )
    despues = sorted(
        [l for l in antes if l.estado != "libre"] + [nueva],
        key=lambda l: l.inicio_bytes
    )

    advertencias = []
    if disco.tipo_tabla == "msdos" and nuevo_num > 4:
        advertencias.append(
            "MBR solo permite 4 particiones primarias. "
            "Considera usar una partición extendida."
        )
    if tamaño_bytes < 32 * 1024 * 1024 and filesystem in ("fat32", "exfat"):
        advertencias.append(
            f"{filesystem.upper()} necesita al menos 32MB para funcionar correctamente."
        )

    cmd = (f"parted -s {disco.ruta} unit MB mkpart primary "
           f"{filesystem} {inicio_mb:.2f} {fin_mb:.2f}")
    if nombre:
        cmd = (f"parted -s {disco.ruta} unit MB mkpart \"{nombre}\" "
               f"{filesystem} {inicio_mb:.2f} {fin_mb:.2f}")

    return ResultadoSimulacion(
        posible=True,
        advertencias=advertencias,
        tabla_antes=antes,
        tabla_despues=despues,
        comando_parted=cmd,
        descripcion=(
            f"Crear partición #{nuevo_num} {filesystem.upper()} "
            f"{tamaño_bytes/1e9:.2f}GB ({inicio_mb:.0f}MB-{fin_mb:.0f}MB)"
        ),
    )


def simular_eliminar_particion(resultado_actual, numero: int) -> ResultadoSimulacion:
    """Simula eliminar una partición."""
    disco = resultado_actual.disco
    particion = next(
        (p for p in resultado_actual.particiones_reales if p.numero == numero),
        None
    )
    if not particion:
        return ResultadoSimulacion(
            posible=False,
            motivo_imposible=f"La partición #{numero} no existe.",
            comando_parted=f"parted -s {disco.ruta} rm {numero}",
        )

    antes = _tabla_a_lineas(resultado_actual)
    despues = []
    for l in antes:
        if l.numero == numero:
            # Convertir en espacio libre
            despues.append(LineaSimulacion(
                numero=None,
                inicio_bytes=l.inicio_bytes,
                fin_bytes=l.fin_bytes,
                tamaño_bytes=l.tamaño_bytes,
                filesystem="libre",
                nombre="",
                flags="",
                estado="eliminada",
            ))
        else:
            despues.append(l)

    advertencias = [
        f"Se elimina la partición #{numero} ({particion.filesystem.upper()}, "
        f"{particion.tamaño_gb:.2f}GB). Los datos se perderán permanentemente."
    ]
    if particion.flags and "boot" in particion.flags:
        advertencias.append(
            "⚠ Esta partición tiene el flag 'boot'. Eliminarla puede impedir el arranque del sistema."
        )

    return ResultadoSimulacion(
        posible=True,
        advertencias=advertencias,
        tabla_antes=antes,
        tabla_despues=despues,
        comando_parted=f"parted -s {disco.ruta} rm {numero}",
        descripcion=(
            f"Eliminar partición #{numero} {particion.filesystem.upper()} "
            f"{particion.tamaño_gb:.2f}GB — IRREVERSIBLE"
        ),
    )


def simular_cambiar_flag(
    resultado_actual, numero: int, flag: str, activar: bool
) -> ResultadoSimulacion:
    """Simula cambiar un flag de partición."""
    disco = resultado_actual.disco
    particion = next(
        (p for p in resultado_actual.particiones_reales if p.numero == numero),
        None
    )
    if not particion:
        return ResultadoSimulacion(
            posible=False,
            motivo_imposible=f"La partición #{numero} no existe.",
            comando_parted="",
        )

    estado = "on" if activar else "off"
    antes = _tabla_a_lineas(resultado_actual)
    despues = []
    for l in antes:
        if l.numero == numero:
            flags_actuales = set(f.strip() for f in l.flags.split(",") if f.strip())
            if activar:
                flags_actuales.add(flag)
            else:
                flags_actuales.discard(flag)
            despues.append(LineaSimulacion(
                numero=l.numero,
                inicio_bytes=l.inicio_bytes,
                fin_bytes=l.fin_bytes,
                tamaño_bytes=l.tamaño_bytes,
                filesystem=l.filesystem,
                nombre=l.nombre,
                flags=", ".join(sorted(flags_actuales)),
                estado="modificada",
            ))
        else:
            despues.append(l)

    advertencias = []
    if flag == "boot" and activar:
        # Verificar que no hay otra partición con boot
        otras_boot = [
            p for p in resultado_actual.particiones_reales
            if p.numero != numero and "boot" in p.flags
        ]
        if otras_boot:
            advertencias.append(
                f"La partición #{otras_boot[0].numero} ya tiene el flag boot. "
                "Normalmente solo una partición debe tener este flag."
            )

    return ResultadoSimulacion(
        posible=True,
        advertencias=advertencias,
        tabla_antes=antes,
        tabla_despues=despues,
        comando_parted=f"parted -s {disco.ruta} set {numero} {flag} {estado}",
        descripcion=(
            f"{'Activar' if activar else 'Desactivar'} flag '{flag}' "
            f"en partición #{numero}"
        ),
    )


def simular_redimensionar_particion(
    resultado_actual,
    numero: int,
    nuevo_fin_mb: float,
) -> ResultadoSimulacion:
    """Simula redimensionar el FIN de una partición.

    parted resizepart mueve el final de la partición sin tocar los datos.
    SOLO ES SEGURO si el espacio que se elimina está vacío — parted no
    verifica esto, solo mueve el puntero de fin en la tabla.

    Para reducir: el espacio al final de la partición debe estar vacío
    (disco desfragmentado, o partición nueva sin datos al final).
    Para ampliar: debe haber espacio libre inmediatamente después.
    """
    disco = resultado_actual.disco
    particion = next(
        (p for p in resultado_actual.particiones_reales if p.numero == numero),
        None
    )
    if not particion:
        return ResultadoSimulacion(
            posible=False,
            motivo_imposible=f"La partición #{numero} no existe.",
            comando_parted="",
        )

    nuevo_fin_bytes = int(nuevo_fin_mb * 1e6)
    tamaño_nuevo = nuevo_fin_bytes - particion.inicio_bytes
    tamaño_diff = nuevo_fin_bytes - particion.fin_bytes

    if tamaño_nuevo < 1048576:  # 1MB mínimo
        return ResultadoSimulacion(
            posible=False,
            motivo_imposible="El tamaño resultante sería menor de 1MB.",
            comando_parted="",
        )

    # Verificar solapamiento con siguiente partición
    particiones_reales = sorted(resultado_actual.particiones_reales,
                                  key=lambda p: p.inicio_bytes)
    idx = next((i for i, p in enumerate(particiones_reales)
                 if p.numero == numero), None)

    if idx is not None and idx + 1 < len(particiones_reales):
        sig = particiones_reales[idx + 1]
        if nuevo_fin_bytes > sig.inicio_bytes:
            return ResultadoSimulacion(
                posible=False,
                motivo_imposible=(
                    f"El nuevo fin ({nuevo_fin_mb:.0f}MB) solapa con la "
                    f"partición #{sig.numero} que empieza en {sig.inicio_mb:.0f}MB."
                ),
                comando_parted="",
            )

    # Construir tabla resultante
    antes = _tabla_a_lineas(resultado_actual)
    despues = []
    for l in antes:
        if l.numero == numero:
            despues.append(LineaSimulacion(
                numero=l.numero,
                inicio_bytes=l.inicio_bytes,
                fin_bytes=nuevo_fin_bytes,
                tamaño_bytes=tamaño_nuevo,
                filesystem=l.filesystem,
                nombre=l.nombre,
                flags=l.flags,
                estado="modificada",
            ))
            # Añadir el espacio que queda libre si se redujo
            if tamaño_diff < 0:
                despues.append(LineaSimulacion(
                    numero=None,
                    inicio_bytes=nuevo_fin_bytes,
                    fin_bytes=particion.fin_bytes,
                    tamaño_bytes=abs(tamaño_diff),
                    filesystem="libre",
                    nombre="",
                    flags="",
                    estado="libre",
                ))
        else:
            despues.append(l)

    advertencias = []
    if tamaño_diff < 0:
        advertencias.append(
            f"REDUCCIÓN de {abs(tamaño_diff)/1e6:.0f}MB. "
            f"Los datos al final de la partición se perderán si el espacio no está vacío. "
            f"Asegúrate de que el disco está desfragmentado y el espacio final libre."
        )
        advertencias.append(
            "Después de redimensionar la partición, el sistema de archivos interno "
            "también debe redimensionarse (resize2fs para ext4, fsck para FAT). "
            "SectorZero solo mueve el límite en la tabla — NO redimensiona el FS interno."
        )
    else:
        advertencias.append(
            f"AMPLIACIÓN de {tamaño_diff/1e6:.0f}MB. "
            f"Después necesitarás redimensionar el sistema de archivos interno "
            f"para que use el espacio añadido."
        )

    accion = "Reducir" if tamaño_diff < 0 else "Ampliar"
    return ResultadoSimulacion(
        posible=True,
        advertencias=advertencias,
        tabla_antes=antes,
        tabla_despues=despues,
        comando_parted=f"parted -s {disco.ruta} unit MB resizepart {numero} {nuevo_fin_mb:.2f}",
        descripcion=(
            f"{accion} partición #{numero} {particion.filesystem.upper()}: "
            f"{particion.fin_mb:.0f}MB → {nuevo_fin_mb:.0f}MB "
            f"({'−' if tamaño_diff < 0 else '+'}{abs(tamaño_diff)/1e6:.0f}MB)"
        ),
    )
