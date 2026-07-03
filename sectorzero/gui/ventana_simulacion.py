"""
ventana_simulacion.py — SectorZero
=====================================
Ventana modal que muestra la simulación de una operación antes de ejecutarla.

Flujo:
  1. Muestra tabla ANTES y tabla DESPUÉS calculada en Python
  2. Muestra el comando exacto que se ejecutará
  3. Muestra advertencias si las hay
  4. Dos botones: [Cancelar] y [Ejecutar — primera confirmación]
  5. Si pulsa Ejecutar: diálogo de segunda confirmación
  6. Solo entonces ejecuta y registra en chain.jsonl
"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import messagebox
from typing import Callable, Optional

from sectorzero.gui.estilos import (
    BG_OSCURO, BG_PANEL, BG_ENTRADA,
    AZUL_ELEC, AZUL_CLARO, VERDE, ROJO, AMARILLO, GRIS, BLANCO, TEXTO,
    MONO, MONO_SM, MONO_LG, PAD, PAD_SM,
)
from sectorzero.core.simulacion import ResultadoSimulacion, LineaSimulacion

# Colores de estado en la tabla de simulación
COLOR_ESTADO = {
    "igual":     TEXTO,
    "nueva":     VERDE,
    "eliminada": ROJO,
    "modificada": AMARILLO,
    "libre":     GRIS,
}

BG_ESTADO = {
    "igual":     BG_OSCURO,
    "nueva":     "#0a2a0a",
    "eliminada": "#2a0a0a",
    "modificada": "#2a1a00",
    "libre":     BG_PANEL,
}

ICONO_ESTADO = {
    "igual":     "  ",
    "nueva":     "＋",
    "eliminada": "✕",
    "modificada": "◎",
    "libre":     "░",
}


def _fmt_gb(bytes_val: int) -> str:
    if bytes_val >= 1e12:
        return f"{bytes_val/1e12:.2f}TB"
    if bytes_val >= 1e9:
        return f"{bytes_val/1e9:.2f}GB"
    if bytes_val >= 1e6:
        return f"{bytes_val/1e6:.0f}MB"
    return f"{bytes_val/1e3:.0f}KB"


class VentanaSimulacion(tk.Toplevel):
    """
    Ventana modal de simulación. Se abre antes de cualquier operación
    que modifique la tabla de particiones.

    Uso:
        v = VentanaSimulacion(parent, sim, on_confirmar=callback_ejecutar)
    """

    def __init__(self, parent, simulacion: ResultadoSimulacion,
                 on_confirmar: Optional[Callable] = None,
                 vidpid: str = "", **kwargs):
        super().__init__(parent, **kwargs)
        self._sim = simulacion
        self._on_confirmar = on_confirmar
        self._vidpid = vidpid
        self._ejecutando = False
        self._letras_unidad: list[str] = []  # se resuelven en background

        self.title("⚠ Simulación de operación — SectorZero")
        self.configure(bg=BG_OSCURO)
        self.geometry("900x680")
        self.minsize(750, 520)
        self.resizable(True, True)
        self.grab_set()

        self._construir()

        # Resolver letras de unidad Windows en background si es redimensionado
        if self._vidpid and "resizepart" in simulacion.comando_parted:
            threading.Thread(target=self._resolver_letras, daemon=True).start()

    def _construir(self):
        # Cabecera
        cab = tk.Frame(self, bg=BG_PANEL)
        cab.pack(fill=tk.X)
        tk.Label(cab, text="Simulación — Vista previa de la operación",
                  bg=BG_PANEL, fg=AZUL_ELEC, font=MONO_LG).pack(
            side=tk.LEFT, padx=PAD, pady=PAD_SM)

        icono = "✓" if self._sim.posible else "✗"
        color = VERDE if self._sim.posible else ROJO
        tk.Label(cab, text=f"{icono} {'Operación posible' if self._sim.posible else 'Operación imposible'}",
                  bg=BG_PANEL, fg=color, font=MONO).pack(
            side=tk.RIGHT, padx=PAD)

        # Descripción de la operación
        tk.Label(self, text=self._sim.descripcion,
                  bg=BG_OSCURO, fg=BLANCO, font=MONO,
                  wraplength=860, justify=tk.LEFT).pack(
            anchor="w", padx=PAD, pady=(PAD_SM, 0))

        # Comando exacto
        frame_cmd = tk.Frame(self, bg=BG_ENTRADA)
        frame_cmd.pack(fill=tk.X, padx=PAD, pady=PAD_SM)
        tk.Label(frame_cmd, text="Comando:", bg=BG_ENTRADA,
                  fg=GRIS, font=MONO_SM).pack(side=tk.LEFT, padx=PAD_SM)
        tk.Label(frame_cmd, text=self._sim.comando_parted,
                  bg=BG_ENTRADA, fg=AZUL_ELEC, font=MONO).pack(
            side=tk.LEFT, padx=PAD_SM, pady=PAD_SM)

        # Advertencias
        if self._sim.advertencias:
            frame_aviso = tk.Frame(self, bg="#1a1a00")
            frame_aviso.pack(fill=tk.X, padx=PAD, pady=(0, PAD_SM))
            for av in self._sim.advertencias:
                tk.Label(frame_aviso, text=f"⚠ {av}",
                          bg="#1a1a00", fg=AMARILLO, font=MONO_SM,
                          wraplength=860, justify=tk.LEFT, anchor="w").pack(
                    fill=tk.X, padx=PAD_SM, pady=1)

        # Aviso especial de desfrag para operaciones de redimensionado
        if "resizepart" in self._sim.comando_parted and "Reducir" in self._sim.descripcion:
            self._construir_aviso_defrag()

        if not self._sim.posible:
            frame_err = tk.Frame(self, bg="#2a0000")
            frame_err.pack(fill=tk.X, padx=PAD, pady=(0, PAD_SM))
            tk.Label(frame_err,
                      text=f"✗ {self._sim.motivo_imposible}",
                      bg="#2a0000", fg=ROJO, font=MONO_SM,
                      wraplength=860, justify=tk.LEFT, anchor="w").pack(
                fill=tk.X, padx=PAD_SM, pady=PAD_SM)

        # Tablas ANTES / DESPUÉS
        frame_tablas = tk.Frame(self, bg=BG_OSCURO)
        frame_tablas.pack(fill=tk.BOTH, expand=True, padx=PAD)
        frame_tablas.columnconfigure(0, weight=1)
        frame_tablas.columnconfigure(1, weight=1)

        self._construir_tabla(frame_tablas, "ANTES", self._sim.tabla_antes, col=0)
        self._construir_tabla(frame_tablas, "DESPUÉS", self._sim.tabla_despues, col=1)

        # Leyenda
        frame_leyenda = tk.Frame(self, bg=BG_PANEL)
        frame_leyenda.pack(fill=tk.X, padx=PAD, pady=(PAD_SM, 0))
        for estado, icono in ICONO_ESTADO.items():
            if estado == "libre":
                continue
            color = COLOR_ESTADO[estado]
            tk.Label(frame_leyenda, text=f"{icono} {estado.capitalize()}",
                      bg=BG_PANEL, fg=color, font=MONO_SM).pack(
                side=tk.LEFT, padx=PAD)

        # Botones
        frame_btns = tk.Frame(self, bg=BG_PANEL, height=52)
        frame_btns.pack(fill=tk.X, side=tk.BOTTOM)
        frame_btns.pack_propagate(False)

        from sectorzero.gui.app import BotonSZ
        BotonSZ(frame_btns, "✕ Cancelar",
                 comando=self.destroy,
                 color=GRIS, ancho=140).pack(side=tk.LEFT, padx=PAD_SM, pady=PAD_SM)

        if self._sim.posible:
            es_destructivo = any(
                w in self._sim.descripcion.upper()
                for w in ("ELIMINAR", "BORRAR", "BORRA", "IRREVERSIBLE", "NUEVA TABLA")
            )
            color_btn = ROJO if es_destructivo else AZUL_ELEC
            texto_btn = "⚠ Ejecutar (operación destructiva)" if es_destructivo else "▶ Ejecutar"

            BotonSZ(frame_btns, texto_btn,
                     comando=self._primera_confirmacion,
                     color=color_btn, ancho=280).pack(
                side=tk.RIGHT, padx=PAD_SM, pady=PAD_SM)

    def _resolver_letras(self):
        """Resuelve las letras de unidad Windows en background y actualiza el comando."""
        try:
            from sectorzero.core.usbipd_utils import obtener_letra_unidad
            letras = obtener_letra_unidad(self._vidpid)
            if letras:
                self._letras_unidad = letras
                # Actualizar el comando de defrag en la UI desde el hilo principal
                self.after(0, self._actualizar_cmd_defrag)
        except Exception:
            pass

    def _actualizar_cmd_defrag(self):
        """Actualiza el widget del comando de defrag con la letra real."""
        if not self._letras_unidad or not hasattr(self, "_caja_defrag"):
            return
        letra = self._letras_unidad[0]
        cmd = f"Optimize-Volume -DriveLetter {letra} -Defrag -Verbose"
        self._caja_defrag.configure(state=tk.NORMAL)
        self._caja_defrag.delete("1.0", tk.END)
        self._caja_defrag.insert("1.0", cmd)
        self._caja_defrag.configure(state=tk.DISABLED)
        # Actualizar el botón
        if hasattr(self, "_btn_defrag_cmd"):
            self._btn_defrag_cmd = cmd

    def _construir_aviso_defrag(self):
        """Aviso de desfragmentación previa para operaciones de reducción."""
        frame = tk.Frame(self, bg="#0a1a0a",
                          relief=tk.FLAT,
                          highlightbackground=VERDE,
                          highlightthickness=1)
        frame.pack(fill=tk.X, padx=PAD, pady=(0, PAD_SM))

        tk.Label(frame,
                  text="📋 PASO PREVIO RECOMENDADO — Desfragmentar en Windows",
                  bg="#0a1a0a", fg=VERDE, font=MONO_SM).pack(
            anchor="w", padx=PAD_SM, pady=(PAD_SM, 2))

        tk.Label(frame,
                  text="Antes de reducir una partición, desfragmenta el disco en Windows\n"
                       "para consolidar los datos al principio y dejar el final vacío.",
                  bg="#0a1a0a", fg=TEXTO, font=MONO_SM,
                  justify=tk.LEFT, anchor="w").pack(
            fill=tk.X, padx=PAD_SM, pady=(0, PAD_SM))

        frame_cmd = tk.Frame(frame, bg="#050f05")
        frame_cmd.pack(fill=tk.X, padx=PAD_SM, pady=(0, PAD_SM))

        # Comando inicial — se actualizará cuando se resuelva la letra
        cmd_inicial = "Optimize-Volume -DriveLetter D -Defrag -Verbose"
        if self._letras_unidad:
            cmd_inicial = f"Optimize-Volume -DriveLetter {self._letras_unidad[0]} -Defrag -Verbose"

        lbl_nota = tk.Label(frame_cmd,
                  text="Detectando letra de unidad..." if not self._letras_unidad
                       else f"Unidad detectada: {self._letras_unidad[0]}:",
                  bg="#050f05", fg=GRIS, font=MONO_SM)
        lbl_nota.pack(anchor="w", padx=PAD_SM, pady=(PAD_SM, 0))

        self._caja_defrag = tk.Text(frame_cmd, height=1, bg=BG_PANEL, fg=VERDE,
                        font=MONO, relief=tk.FLAT, padx=8, pady=4,
                        wrap=tk.NONE, state=tk.NORMAL)
        self._caja_defrag.insert("1.0", cmd_inicial)
        self._caja_defrag.configure(state=tk.DISABLED)
        self._caja_defrag.pack(fill=tk.X, padx=PAD_SM, pady=PAD_SM)

        self._btn_defrag_cmd = cmd_inicial

        from sectorzero.gui.app import BotonSZ

        def _abrir_defrag():
            import subprocess, platform
            cmd = self._btn_defrag_cmd
            if platform.system() == "Windows":
                subprocess.Popen(
                    ["powershell.exe", "-NoExit", "-Command", cmd],
                    creationflags=subprocess.CREATE_NEW_CONSOLE,
                )

        frame_btn = tk.Frame(frame, bg="#0a1a0a")
        frame_btn.pack(fill=tk.X, padx=PAD_SM, pady=(0, PAD_SM))

        BotonSZ(frame_btn, "▶ Abrir PowerShell y desfragmentar",
                 comando=_abrir_defrag,
                 color=VERDE, ancho=280).pack(side=tk.LEFT)

        tk.Label(frame_btn,
                  text="  Espera a que termine antes de ejecutar el redimensionado.",
                  bg="#0a1a0a", fg=GRIS, font=MONO_SM).pack(
            side=tk.LEFT, padx=PAD_SM)

    def _construir_tabla(self, parent, titulo: str,
                          lineas: list[LineaSimulacion], col: int):
        """Construye una columna de tabla (ANTES o DESPUÉS)."""
        frame = tk.Frame(parent, bg=BG_OSCURO)
        frame.grid(row=0, column=col, sticky="nsew", padx=(0 if col else 0, PAD_SM if col == 0 else 0))

        tk.Label(frame, text=titulo, bg=BG_OSCURO,
                  fg=AZUL_ELEC if titulo == "DESPUÉS" else GRIS,
                  font=MONO).pack(anchor="w", pady=(0, 2))

        # Cabecera
        cab = tk.Frame(frame, bg=BG_PANEL)
        cab.pack(fill=tk.X)
        for texto, ancho in [(" ", 2), ("#", 3), ("Inicio", 9),
                               ("Fin", 9), ("Tamaño", 9), ("FS", 8), ("Flags", 8)]:
            tk.Label(cab, text=texto, bg=BG_PANEL, fg=AZUL_ELEC,
                      font=MONO_SM, width=ancho, anchor="w").pack(
                side=tk.LEFT, padx=2, pady=2)

        # Filas
        canvas = tk.Canvas(frame, bg=BG_OSCURO, highlightthickness=0, height=200)
        sb = tk.Scrollbar(frame, orient="vertical", command=canvas.yview)
        frame_filas = tk.Frame(canvas, bg=BG_OSCURO)
        frame_filas.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=frame_filas, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        for linea in lineas:
            bg = BG_ESTADO.get(linea.estado, BG_OSCURO)
            fg = COLOR_ESTADO.get(linea.estado, TEXTO)
            icono = ICONO_ESTADO.get(linea.estado, " ")
            fila = tk.Frame(frame_filas, bg=bg)
            fila.pack(fill=tk.X)

            num_str = str(linea.numero) if linea.numero else "—"
            for texto, ancho in [
                (icono, 2),
                (num_str, 3),
                (f"{linea.inicio_mb:.0f}M", 9),
                (f"{linea.fin_mb:.0f}M", 9),
                (_fmt_gb(linea.tamaño_bytes), 9),
                ((linea.filesystem or "?")[:8].upper(), 8),
                ((linea.flags or "")[:8], 8),
            ]:
                tk.Label(fila, text=texto, bg=bg, fg=fg,
                          font=MONO_SM, width=ancho, anchor="w").pack(
                    side=tk.LEFT, padx=2, pady=1)

    def _primera_confirmacion(self):
        """Primera confirmación — muestra lo que va a pasar."""
        es_destructivo = any(
            w in self._sim.descripcion.upper()
            for w in ("ELIMINAR", "BORRAR", "BORRA", "IRREVERSIBLE", "NUEVA TABLA")
        )

        msg = (
            f"Vas a ejecutar:\n\n"
            f"  {self._sim.descripcion}\n\n"
            f"Comando:\n"
            f"  {self._sim.comando_parted}\n\n"
        )
        if es_destructivo:
            msg += "⚠ Esta operación es IRREVERSIBLE.\n\n"
        msg += "¿Confirmas?"

        if not messagebox.askyesno(
            "Primera confirmación",
            msg,
            icon="warning" if es_destructivo else "question",
        ):
            return

        self._segunda_confirmacion(es_destructivo)

    def _segunda_confirmacion(self, es_destructivo: bool):
        """Segunda confirmación — última oportunidad."""
        if es_destructivo:
            msg = (
                "ÚLTIMA OPORTUNIDAD.\n\n"
                f"{self._sim.descripcion}\n\n"
                "Esta acción no se puede deshacer.\n"
                "¿Ejecutar definitivamente?"
            )
        else:
            msg = (
                f"Confirma la ejecución:\n\n"
                f"{self._sim.comando_parted}\n\n"
                f"¿Ejecutar?"
            )

        if not messagebox.askyesno(
            "Segunda confirmación — Ejecutar",
            msg,
            icon="warning" if es_destructivo else "question",
        ):
            return

        self._ejecutar()

    def _ejecutar(self):
        """Ejecuta la operación real tras las dos confirmaciones."""
        if self._ejecutando:
            return
        self._ejecutando = True

        # Cambiar el botón a estado "ejecutando"
        self.configure(cursor="wait")

        if self._on_confirmar:
            self._on_confirmar(self._sim)

        self.destroy()
