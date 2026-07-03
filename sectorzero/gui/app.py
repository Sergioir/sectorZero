"""
app.py — SectorZero
====================
Ventana principal de SectorZero.

Layout:
  ┌─ Cabecera: nombre + selector de disco + botones ────────────┐
  ├─ Barra visual del disco (proporcional) ─────────────────────┤
  ├─ Panel izquierdo: info disco + estado MBR ──────────────────┤
  │  Panel derecho: tabla de particiones ───────────────────────┤
  ├─ Barra de operaciones ──────────────────────────────────────┤
  └─ Log de operaciones ────────────────────────────────────────┘
"""

from __future__ import annotations

import queue
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, simpledialog
import tkinter.simpledialog as tk_simpledialog
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sectorzero.gui.estilos import (
    BG_OSCURO, BG_PANEL, BG_ENTRADA,
    AZUL_ELEC, AZUL_CLARO, AZUL_DIM,
    VERDE, ROJO, AMARILLO, GRIS, BLANCO, TEXTO,
    COLORES_FS, MONO, MONO_SM, MONO_LG, TITULO, NORMAL,
    PAD, PAD_SM,
)


# ------------------------------------------------------------------
# Widgets base
# ------------------------------------------------------------------

class BotonSZ(tk.Canvas):
    """Botón estilo SectorZero."""
    def __init__(self, parent, texto, comando=None,
                 color=AZUL_ELEC, ancho=160, alto=32, **kwargs):
        super().__init__(parent, width=ancho, height=alto,
                         bg=BG_OSCURO, highlightthickness=0, **kwargs)
        self._texto = texto
        self._cmd = comando
        self._color = color
        self._ancho = ancho
        self._alto = alto
        self._activo = True
        self._dibujar(BG_PANEL)
        self.bind("<Enter>", lambda e: self._dibujar(AZUL_DIM) if self._activo else None)
        self.bind("<Leave>", lambda e: self._dibujar(BG_PANEL))
        self.bind("<Button-1>", self._click)

    def _dibujar(self, fondo):
        self.delete("all")
        self.create_rectangle(0, 0, self._ancho, self._alto,
                               fill=fondo, outline=self._color if self._activo else GRIS, width=1)
        self.create_text(self._ancho // 2, self._alto // 2,
                          text=self._texto,
                          fill=self._color if self._activo else GRIS,
                          font=MONO_SM)

    def _click(self, e):
        if self._activo and self._cmd:
            self._cmd()

    def activar(self):
        self._activo = True
        self._dibujar(BG_PANEL)

    def desactivar(self):
        self._activo = False
        self._dibujar(BG_PANEL)


class AreaLog(tk.Frame):
    """Área de log scrollable."""
    COLORES = {"ok": VERDE, "error": ROJO, "aviso": AMARILLO,
                "gris": GRIS, "info": AZUL_CLARO}

    def __init__(self, parent, alto=120, **kwargs):
        super().__init__(parent, bg=BG_OSCURO, **kwargs)
        self._txt = tk.Text(self, height=alto // 16, bg=BG_ENTRADA,
                             fg=TEXTO, font=MONO_SM, wrap=tk.WORD,
                             state=tk.DISABLED, relief=tk.FLAT, padx=8, pady=4)
        sb = tk.Scrollbar(self, command=self._txt.yview, bg=BG_PANEL)
        self._txt.configure(yscrollcommand=sb.set)
        for nivel, color in self.COLORES.items():
            self._txt.tag_configure(nivel, foreground=color)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self._txt.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    def escribir(self, texto, nivel="gris"):
        self._txt.configure(state=tk.NORMAL)
        self._txt.insert(tk.END, texto + "\n", nivel)
        self._txt.see(tk.END)
        self._txt.configure(state=tk.DISABLED)

    def limpiar(self):
        self._txt.configure(state=tk.NORMAL)
        self._txt.delete("1.0", tk.END)
        self._txt.configure(state=tk.DISABLED)


class BarraVisualDisco(tk.Canvas):
    """
    Barra proporcional del disco — el corazón visual de SectorZero.
    Muestra cada partición como un bloque coloreado según su FS,
    con etiqueta de nombre y tamaño. El espacio libre aparece en oscuro.
    """

    def __init__(self, parent, alto=60, **kwargs):
        super().__init__(parent, height=alto, bg=BG_OSCURO,
                         highlightthickness=1, highlightbackground=GRIS, **kwargs)
        self._alto = alto
        self._resultado = None
        self._on_click_particion = None
        self.bind("<Configure>", lambda e: self._redibujar())
        self.bind("<Button-1>", self._on_click)

    def actualizar(self, resultado, on_click=None):
        self._resultado = resultado
        self._on_click_particion = on_click
        self._redibujar()

    def _redibujar(self):
        self.delete("all")
        if not self._resultado or not self._resultado.disco:
            self.create_text(self.winfo_width() // 2, self._alto // 2,
                              text="Sin disco seleccionado", fill=GRIS, font=MONO_SM)
            return

        w = self.winfo_width()
        if w <= 1:
            return

        total = self._resultado.disco.tamaño_bytes
        if total <= 0:
            return

        # Dibujar fondo (espacio no mapeado)
        self.create_rectangle(0, 0, w, self._alto, fill=BG_PANEL, outline="")

        # Dibujar cada partición y espacio libre
        self._segmentos = []  # (x_inicio, x_fin, particion)

        for part in self._resultado.particiones:
            x_ini = int(part.inicio_bytes / total * w)
            x_fin = int(part.fin_bytes / total * w)
            if x_fin <= x_ini:
                x_fin = x_ini + 1

            fs = part.filesystem.lower() if part.filesystem else ""
            color = COLORES_FS.get(fs, COLORES_FS["unknown"])

            # Rectángulo de la partición
            self.create_rectangle(x_ini, 2, x_fin, self._alto - 2,
                                   fill=color, outline=BG_OSCURO, width=1)

            self._segmentos.append((x_ini, x_fin, part))

            # Etiqueta si hay espacio suficiente
            ancho_seg = x_fin - x_ini
            if ancho_seg > 40 and not part.es_libre:
                fs_label = part.filesystem.upper() if part.filesystem else "?"
                gb_label = f"{part.tamaño_gb:.1f}G"
                # Texto en dos líneas si hay espacio
                if ancho_seg > 80:
                    self.create_text(
                        (x_ini + x_fin) // 2, self._alto // 2 - 8,
                        text=fs_label, fill=BG_OSCURO, font=MONO_SM, anchor="center"
                    )
                    self.create_text(
                        (x_ini + x_fin) // 2, self._alto // 2 + 8,
                        text=gb_label, fill=BG_OSCURO, font=MONO_SM, anchor="center"
                    )
                else:
                    self.create_text(
                        (x_ini + x_fin) // 2, self._alto // 2,
                        text=gb_label, fill=BG_OSCURO, font=MONO_SM, anchor="center"
                    )

        # Separadores de sector
        self.create_line(0, 0, w, 0, fill=GRIS, width=1)
        self.create_line(0, self._alto - 1, w, self._alto - 1, fill=GRIS, width=1)

    def _on_click(self, event):
        if not self._segmentos or not self._on_click_particion:
            return
        x = event.x
        for x_ini, x_fin, part in self._segmentos:
            if x_ini <= x <= x_fin:
                self._on_click_particion(part)
                return


# ------------------------------------------------------------------
# Workers
# ------------------------------------------------------------------

def _evento(tipo, **datos):
    return {"tipo": tipo, **datos}


def worker_leer_disco(cola, ruta, distro):
    try:
        from sectorzero.core.disco import leer_disco
        resultado = leer_disco(ruta, distro=distro)
        cola.put(_evento("disco_leido", resultado=resultado))
    except Exception as ex:
        cola.put(_evento("error", mensaje=str(ex)))


def worker_listar_discos(cola, distro):
    try:
        from sectorzero.core.disco import listar_discos_wsl
        discos = listar_discos_wsl(distro=distro)
        cola.put(_evento("discos_listados", discos=discos))
    except Exception as ex:
        cola.put(_evento("error", mensaje=str(ex)))

# ------------------------------------------------------------------
# Ventana principal
# ------------------------------------------------------------------

class AppSectorZero(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title("SectorZero — Gestión de particiones")
        self.configure(bg=BG_OSCURO)
        self.geometry("980x660")
        self.resizable(True, True)
        self.minsize(800, 520)

        self._cola: queue.Queue = queue.Queue()
        self._resultado_actual = None
        self._particion_seleccionada = None
        self._disco_actual: Optional[str] = None
        self._distro: Optional[str] = None

        self._iniciar_cola()
        self._mostrar_setup()

    def _mostrar_setup(self):
        """Muestra la pantalla de dependencias antes de la app principal."""
        from sectorzero.gui.pantalla_setup import PantallaSetup
        self._frame_setup = PantallaSetup(self, on_completo=self._setup_completado)
        self._frame_setup.pack(fill=tk.BOTH, expand=True)

    def _setup_completado(self):
        """Tras el setup, muestra la pantalla de conexión USB."""
        self._frame_setup.destroy()
        self._mostrar_usb()

    def _mostrar_usb(self):
        """Pantalla de conexión USB — opcional, el usuario puede saltarla."""
        from sectorzero.gui.pantalla_usb import PantallaUSB
        self._frame_usb = PantallaUSB(
            self, on_continuar=self._usb_completado, distro=self._distro)
        self._frame_usb.pack(fill=tk.BOTH, expand=True)

    def _usb_completado(self):
        """Tras conectar USB, muestra la pantalla principal."""
        self._frame_usb.destroy()
        self._construir()
        self._listar_discos()

    # ------------------------------------------------------------------
    # Construcción de la UI
    # ------------------------------------------------------------------

    def _construir(self):
        self._construir_cabecera()
        self._construir_barra_disco()
        self._construir_paneles()
        self._construir_operaciones()
        self._construir_log()

    def _construir_cabecera(self):
        cab = tk.Frame(self, bg=BG_PANEL, height=52)
        cab.pack(fill=tk.X, side=tk.TOP)
        cab.pack_propagate(False)

        tk.Label(cab, text="◈ SECTOR ZERO",
                  bg=BG_PANEL, fg=AZUL_ELEC, font=TITULO).pack(
            side=tk.LEFT, padx=PAD, pady=PAD_SM)

        # Selector de disco
        frame_sel = tk.Frame(cab, bg=BG_PANEL)
        frame_sel.pack(side=tk.LEFT, padx=PAD)

        tk.Label(frame_sel, text="Disco:", bg=BG_PANEL,
                  fg=GRIS, font=MONO_SM).pack(side=tk.LEFT)

        self._var_disco = tk.StringVar(value="")
        self._combo_disco = tk.OptionMenu(frame_sel, self._var_disco, "")
        self._combo_disco.configure(
            bg=BG_PANEL, fg=AZUL_CLARO, font=MONO_SM,
            highlightthickness=0, relief=tk.FLAT,
            activebackground=AZUL_DIM,
        )
        self._combo_disco["menu"].configure(bg=BG_PANEL, fg=AZUL_CLARO, font=MONO_SM)
        self._combo_disco.pack(side=tk.LEFT, padx=PAD_SM)
        self._var_disco.trace_add("write", lambda *a: self._on_disco_cambiado())

        BotonSZ(cab, "↺ Actualizar", comando=self._listar_discos,
                 color=AMARILLO, ancho=120).pack(side=tk.LEFT, padx=PAD_SM, pady=PAD_SM)

        BotonSZ(cab, "● Conectar USB", comando=self._conectar_usb,
                 color=AZUL_ELEC, ancho=140).pack(side=tk.LEFT, padx=PAD_SM, pady=PAD_SM)

        # Versión + indicador de modo
        self._lbl_modo = tk.Label(cab, text="",
                                   bg=BG_PANEL, fg=GRIS, font=MONO_SM)
        self._lbl_modo.pack(side=tk.RIGHT, padx=PAD)

        tk.Label(cab, text="v0.1.0", bg=BG_PANEL,
                  fg=GRIS, font=MONO_SM).pack(side=tk.RIGHT, padx=(0, PAD_SM))

    def _construir_barra_disco(self):
        """Barra visual proporcional del disco."""
        frame = tk.Frame(self, bg=BG_OSCURO)
        frame.pack(fill=tk.X, padx=PAD, pady=(PAD_SM, 0))

        tk.Label(frame, text="Mapa del disco",
                  bg=BG_OSCURO, fg=GRIS, font=MONO_SM).pack(anchor="w")

        self._barra = BarraVisualDisco(frame, alto=56)
        self._barra.pack(fill=tk.X, pady=(2, 0))

    def _construir_paneles(self):
        """Panel izquierdo (info disco) + Panel derecho (tabla particiones)."""
        frame_paneles = tk.Frame(self, bg=BG_OSCURO)
        frame_paneles.pack(fill=tk.BOTH, expand=True, padx=PAD, pady=PAD_SM)

        # Panel izquierdo — info disco y estado MBR
        self._panel_izq = tk.Frame(frame_paneles, bg=BG_PANEL, width=280)
        self._panel_izq.pack(side=tk.LEFT, fill=tk.Y, padx=(0, PAD_SM))
        self._panel_izq.pack_propagate(False)

        tk.Label(self._panel_izq, text="Disco",
                  bg=BG_PANEL, fg=AZUL_ELEC, font=MONO).pack(
            anchor="w", padx=PAD_SM, pady=(PAD_SM, 0))

        self._lbl_info_disco = tk.Label(
            self._panel_izq,
            text="Sin disco seleccionado",
            bg=BG_PANEL, fg=GRIS, font=MONO_SM,
            justify=tk.LEFT, anchor="w", wraplength=260,
        )
        self._lbl_info_disco.pack(anchor="w", padx=PAD_SM, pady=PAD_SM)

        tk.Frame(self._panel_izq, bg=GRIS, height=1).pack(fill=tk.X, padx=PAD_SM)

        tk.Label(self._panel_izq, text="Sector de arranque",
                  bg=BG_PANEL, fg=AZUL_ELEC, font=MONO).pack(
            anchor="w", padx=PAD_SM, pady=(PAD_SM, 0))

        self._lbl_mbr = tk.Label(
            self._panel_izq,
            text="—",
            bg=BG_PANEL, fg=GRIS, font=MONO_SM,
            justify=tk.LEFT, anchor="w", wraplength=260,
        )
        self._lbl_mbr.pack(anchor="w", padx=PAD_SM, pady=PAD_SM)

        # Leyenda de colores
        tk.Frame(self._panel_izq, bg=GRIS, height=1).pack(fill=tk.X, padx=PAD_SM)
        tk.Label(self._panel_izq, text="Leyenda",
                  bg=BG_PANEL, fg=AZUL_ELEC, font=MONO).pack(
            anchor="w", padx=PAD_SM, pady=(PAD_SM, 0))

        frame_leyenda = tk.Frame(self._panel_izq, bg=BG_PANEL)
        frame_leyenda.pack(fill=tk.X, padx=PAD_SM)
        for fs, color in [("exFAT", COLORES_FS["exfat"]),
                           ("NTFS", COLORES_FS["ntfs"]),
                           ("FAT32", COLORES_FS["fat32"]),
                           ("ext4", COLORES_FS["ext4"]),
                           ("Libre", COLORES_FS["libre"])]:
            f = tk.Frame(frame_leyenda, bg=BG_PANEL)
            f.pack(anchor="w", pady=1)
            tk.Canvas(f, width=14, height=14, bg=color,
                       highlightthickness=0).pack(side=tk.LEFT, padx=(0, 4))
            tk.Label(f, text=fs, bg=BG_PANEL, fg=GRIS, font=MONO_SM).pack(side=tk.LEFT)

        # Panel derecho — tabla de particiones
        panel_der = tk.Frame(frame_paneles, bg=BG_OSCURO)
        panel_der.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        tk.Label(panel_der, text="Particiones",
                  bg=BG_OSCURO, fg=AZUL_ELEC, font=MONO).pack(anchor="w")

        # Cabecera de la tabla
        frame_cab_tabla = tk.Frame(panel_der, bg=BG_PANEL)
        frame_cab_tabla.pack(fill=tk.X, pady=(2, 0))

        for texto, ancho in [
            ("#", 3), ("Inicio", 12), ("Fin", 12),
            ("Tamaño", 10), ("FS", 8), ("Nombre", 14), ("Flags", 10)
        ]:
            tk.Label(frame_cab_tabla, text=texto, bg=BG_PANEL,
                      fg=AZUL_ELEC, font=MONO_SM, width=ancho, anchor="w").pack(
                side=tk.LEFT, padx=2, pady=2)

        # Lista de particiones con scroll
        frame_lista = tk.Frame(panel_der, bg=BG_OSCURO)
        frame_lista.pack(fill=tk.BOTH, expand=True, pady=2)

        self._canvas_tabla = tk.Canvas(frame_lista, bg=BG_OSCURO, highlightthickness=0)
        sb_tabla = tk.Scrollbar(frame_lista, orient="vertical",
                                 command=self._canvas_tabla.yview)
        self._frame_filas = tk.Frame(self._canvas_tabla, bg=BG_OSCURO)
        self._frame_filas.bind(
            "<Configure>",
            lambda e: self._canvas_tabla.configure(
                scrollregion=self._canvas_tabla.bbox("all"))
        )
        self._canvas_tabla.create_window((0, 0), window=self._frame_filas, anchor="nw")
        self._canvas_tabla.configure(yscrollcommand=sb_tabla.set)
        sb_tabla.pack(side=tk.RIGHT, fill=tk.Y)
        self._canvas_tabla.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Partición seleccionada
        self._lbl_sel = tk.Label(panel_der,
                                   text="Pulsa en una partición para seleccionarla",
                                   bg=BG_OSCURO, fg=GRIS, font=MONO_SM)
        self._lbl_sel.pack(anchor="w", pady=(PAD_SM, 0))

    def _construir_operaciones(self):
        """Barra de operaciones — desactivada hasta tener un disco."""
        frame_ops = tk.Frame(self, bg=BG_PANEL, height=44)
        frame_ops.pack(fill=tk.X, padx=PAD, pady=PAD_SM)
        frame_ops.pack_propagate(False)

        tk.Label(frame_ops, text="Operaciones:",
                  bg=BG_PANEL, fg=GRIS, font=MONO_SM).pack(
            side=tk.LEFT, padx=PAD_SM, pady=PAD_SM)

        self._btn_nueva_tabla = BotonSZ(frame_ops, "Nueva tabla",
                                         comando=self._op_nueva_tabla,
                                         color=AMARILLO, ancho=120)
        self._btn_nueva_tabla.pack(side=tk.LEFT, padx=2, pady=PAD_SM)

        self._btn_nueva_part = BotonSZ(frame_ops, "+ Partición",
                                        comando=self._op_nueva_particion,
                                        color=AZUL_ELEC, ancho=120)
        self._btn_nueva_part.pack(side=tk.LEFT, padx=2, pady=PAD_SM)

        self._btn_eliminar = BotonSZ(frame_ops, "✕ Eliminar",
                                      comando=self._op_eliminar,
                                      color=ROJO, ancho=110)
        self._btn_eliminar.pack(side=tk.LEFT, padx=2, pady=PAD_SM)

        self._btn_flag = BotonSZ(frame_ops, "⚑ Flag",
                                  comando=self._op_flag,
                                  color=GRIS, ancho=90)
        self._btn_flag.pack(side=tk.LEFT, padx=2, pady=PAD_SM)

        self._btn_reparar_mbr = BotonSZ(frame_ops, "⚕ Reparar MBR",
                                          comando=self._op_reparar_mbr,
                                          color=VERDE, ancho=150)
        self._btn_reparar_mbr.pack(side=tk.LEFT, padx=2, pady=PAD_SM)

        # Desactivar todo hasta tener disco
        for btn in [self._btn_nueva_tabla, self._btn_nueva_part,
                     self._btn_eliminar, self._btn_flag, self._btn_reparar_mbr]:
            btn.desactivar()

    def _construir_log(self):
        tk.Label(self, text="Log", bg=BG_OSCURO, fg=GRIS, font=MONO_SM).pack(
            anchor="w", padx=PAD)
        self._log = AreaLog(self, alto=80)
        self._log.pack(fill=tk.X, padx=PAD, pady=(0, PAD))

    # ------------------------------------------------------------------
    # Cola de eventos (pattern sin ColaMixin para simplicidad)
    # ------------------------------------------------------------------

    def _iniciar_cola(self):
        self._procesar_cola()

    def _procesar_cola(self):
        try:
            while True:
                ev = self._cola.get_nowait()
                self._on_evento(ev)
        except queue.Empty:
            pass
        finally:
            self.after(50, self._procesar_cola)

    def _lanzar_worker(self, fn, *args):
        import threading
        def _run():
            try:
                fn(self._cola, *args)
            except Exception as e:
                self._cola.put(_evento("error", mensaje=str(e)))
        threading.Thread(target=_run, daemon=True).start()

    def _on_evento(self, ev):
        tipo = ev.get("tipo")

        if tipo == "discos_listados":
            self._actualizar_combo_discos(ev["discos"])

        elif tipo == "disco_leido":
            self._mostrar_resultado(ev["resultado"])

        elif tipo == "error":
            self._log.escribir(f"Error: {ev['mensaje']}", "error")

        elif tipo == "operacion_ok":
            self._log.escribir(f"✓ {ev.get('mensaje', 'Operación completada.')}", "ok")
            self._recargar_disco()

        elif tipo == "operacion_error":
            self._log.escribir(f"✗ {ev.get('mensaje', 'Error en la operación.')}", "error")

    # ------------------------------------------------------------------
    # Lógica principal
    # ------------------------------------------------------------------

    def _listar_discos(self):
        self._log.escribir("Listando discos en WSL...", "gris")
        self._lanzar_worker(worker_listar_discos, self._distro)

    def _actualizar_combo_discos(self, discos: list):
        menu = self._combo_disco["menu"]
        menu.delete(0, "end")

        if not discos:
            self._var_disco.set("")
            self._log.escribir("No se encontraron discos en WSL.", "aviso")
            return

        fisicos = [d for d in discos if not d.get("es_virtual_wsl")]
        virtuales = [d for d in discos if d.get("es_virtual_wsl")]

        # Mostrar TODOS los discos — internos en solo lectura, no ocultarlos
        def _label(d):
            base = d["label"]
            return base + "  [solo lectura]" if d.get("es_virtual_wsl") else base

        self._mapa_discos = {_label(d): d["ruta"] for d in discos}
        self._mapa_discos_info = {d["ruta"]: d for d in discos}

        for d in discos:
            label = _label(d)
            menu.add_command(label=label,
                              command=lambda v=label: self._var_disco.set(v))

        # Seleccionar primer físico por defecto, o el primero disponible
        primero = fisicos[0] if fisicos else discos[0]
        self._var_disco.set(_label(primero))
        self._log.escribir(
            f"{len(fisicos)} disco(s) físico(s) + {len(virtuales)} interno(s) de WSL",
            "info")

    def _on_disco_cambiado(self):
        label = self._var_disco.get()
        if not label:
            return
        # Traducir label legible a ruta WSL real
        ruta = getattr(self, "_mapa_discos", {}).get(label, label)
        if ruta and ruta != self._disco_actual:
            self._disco_actual = ruta
            self._recargar_disco()

    def _recargar_disco(self):
        if not self._disco_actual:
            return
        self._log.escribir(f"Leyendo {self._disco_actual}...", "gris")
        self._lanzar_worker(worker_leer_disco, self._disco_actual, self._distro)

    def _mostrar_resultado(self, resultado):
        self._resultado_actual = resultado

        if not resultado.ejecucion_correcta:
            self._log.escribir(f"Error: {resultado.error}", "error")
            return

        # Barra visual
        self._barra.actualizar(resultado, on_click=self._on_click_particion)

        # Info disco
        if resultado.disco:
            d = resultado.disco
            info = (
                f"{d.ruta}\n"
                f"{d.tamaño_gb:.1f} GB\n"
                f"Tabla: {d.tipo_tabla_legible}\n"
                f"Transporte: {d.transport or '?'}\n"
                f"Sector: {d.sector_logico}B / {d.sector_fisico}B\n"
                f"Modelo: {d.modelo or '?'}"
            )
            self._lbl_info_disco.config(text=info, fg=TEXTO)

        # Estado MBR
        if resultado.estado_mbr:
            mbr = resultado.estado_mbr
            color = {"ok": VERDE, "aviso": AMARILLO, "error": ROJO}[mbr.estado_visual]
            self._lbl_mbr.config(text=mbr.descripcion, fg=color)
        else:
            self._lbl_mbr.config(text="No leído", fg=GRIS)

        # Tabla de particiones
        self._poblar_tabla(resultado)

        # Determinar si el disco es USB externo o interno
        disco_info = getattr(self, "_mapa_discos_info", {})
        info_disco_sel = disco_info.get(self._disco_actual, {})
        es_usb = (info_disco_sel.get("removible", False) or
                   info_disco_sel.get("transport", "") == "usb")
        self._disco_es_usb = es_usb

        if es_usb:
            # USB externo — operaciones completas
            for btn in [self._btn_nueva_tabla, self._btn_nueva_part,
                         self._btn_flag, self._btn_reparar_mbr]:
                btn.activar()
            if resultado.particiones_reales:
                self._btn_eliminar.activar()
            self._lbl_modo.config(text="● USB — edición habilitada", fg=VERDE)
            self._log.escribir("Disco USB externo — operaciones habilitadas.", "ok")
        else:
            # Disco interno — solo lectura
            for btn in [self._btn_nueva_tabla, self._btn_nueva_part,
                         self._btn_eliminar, self._btn_flag, self._btn_reparar_mbr]:
                btn.desactivar()
            self._lbl_modo.config(text="● Interno — solo lectura", fg=AMARILLO)
            self._log.escribir(
                "Disco interno — solo lectura (las operaciones están desactivadas).", "aviso")

        n = len(resultado.particiones_reales)
        libre_gb = resultado.espacio_libre_bytes / 1e9
        self._log.escribir(
            f"Disco leído: {n} partición(es), {libre_gb:.1f} GB libres.", "ok")

    def _poblar_tabla(self, resultado):
        for w in self._frame_filas.winfo_children():
            w.destroy()

        self._filas_particion = {}

        for i, part in enumerate(resultado.particiones):
            bg = BG_OSCURO if i % 2 == 0 else BG_PANEL
            fila = tk.Frame(self._frame_filas, bg=bg, cursor="hand2")
            fila.pack(fill=tk.X)

            # Color indicador del FS
            fs = part.filesystem.lower() if part.filesystem else ""
            color_fs = COLORES_FS.get(fs, COLORES_FS["unknown"])
            tk.Canvas(fila, width=4, height=20, bg=color_fs,
                       highlightthickness=0).pack(side=tk.LEFT)

            num = str(part.numero) if not part.es_libre else "—"
            fs_label = part.filesystem.upper() if part.filesystem else "?"
            if part.es_libre:
                fs_label = "LIBRE"
                fg_fila = GRIS
            else:
                fg_fila = TEXTO

            for texto, ancho in [
                (num, 3),
                (f"{part.inicio_mb:.0f}M", 12),
                (f"{part.fin_mb:.0f}M", 12),
                (f"{part.tamaño_gb:.2f}G", 10),
                (fs_label[:8], 8),
                ((part.nombre or "")[:14], 14),
                ((part.flags or "")[:10], 10),
            ]:
                lbl = tk.Label(fila, text=texto, bg=bg, fg=fg_fila,
                                font=MONO_SM, width=ancho, anchor="w")
                lbl.pack(side=tk.LEFT, padx=2, pady=1)
                lbl.bind("<Button-1>", lambda e, p=part: self._on_click_particion(p))

            fila.bind("<Button-1>", lambda e, p=part: self._on_click_particion(p))
            if not part.es_libre:
                self._filas_particion[part.numero] = fila

    def _on_click_particion(self, part):
        self._particion_seleccionada = part
        # Resaltar fila seleccionada
        for num, fila in self._filas_particion.items():
            color = AZUL_DIM if num == part.numero else (
                BG_OSCURO if list(self._filas_particion.keys()).index(num) % 2 == 0 else BG_PANEL
            )
            fila.configure(bg=color)
            for w in fila.winfo_children():
                if isinstance(w, tk.Label):
                    w.configure(bg=color)

        if part.es_libre:
            self._lbl_sel.config(
                text=f"Espacio libre: {part.tamaño_gb:.2f} GB ({part.inicio_mb:.0f}M - {part.fin_mb:.0f}M)",
                fg=GRIS)
        else:
            self._lbl_sel.config(
                text=f"Seleccionada: #{part.numero} {part.filesystem.upper()} {part.tamaño_gb:.2f} GB",
                fg=AZUL_CLARO)

    def _conectar_usb(self):
        """Abre la pantalla de conexión USB como ventana secundaria."""
        from sectorzero.gui.pantalla_usb import PantallaUSB
        ventana = tk.Toplevel(self)
        ventana.title("Conectar USB a WSL")
        ventana.configure(bg=BG_OSCURO)
        ventana.geometry("820x480")
        ventana.minsize(700, 380)

        def _cerrar_y_actualizar():
            ventana.destroy()
            self._listar_discos()  # Refrescar la lista de discos tras conectar

        PantallaUSB(ventana, on_continuar=_cerrar_y_actualizar,
                     distro=self._distro).pack(fill=tk.BOTH, expand=True)

    # ------------------------------------------------------------------
    # Operaciones (con confirmación)
    # ------------------------------------------------------------------

    def _confirmar(self, titulo, mensaje, destructivo=False) -> bool:
        icon = "warning" if destructivo else "question"
        return messagebox.askyesno(titulo, mensaje, icon=icon)

    def _op_nueva_tabla(self):
        if not self._resultado_actual or not self._resultado_actual.disco:
            return
        tipo = tk.simpledialog.askstring(
            "Nueva tabla", "Tipo: 'gpt' (recomendado) o 'msdos' (MBR clásico):",
            initialvalue="gpt",
        )
        if not tipo or tipo.lower() not in ("gpt", "msdos"):
            return
        from sectorzero.core.simulacion import simular_crear_tabla
        from sectorzero.gui.ventana_simulacion import VentanaSimulacion
        sim = simular_crear_tabla(self._resultado_actual, tipo.lower())
        VentanaSimulacion(self, sim, on_confirmar=self._ejecutar_operacion)

    def _op_nueva_particion(self):
        if not self._resultado_actual or not self._resultado_actual.disco:
            return
        disco_mb = self._resultado_actual.disco.tamaño_bytes / 1e6
        inicio = tk.simpledialog.askfloat(
            "Nueva partición — Inicio (MB)",
            f"Disco: {self._resultado_actual.disco.tamaño_gb:.1f}GB\n"
            f"Inicio (MB, 1-{disco_mb:.0f}):",
            minvalue=1, maxvalue=disco_mb,
        )
        if inicio is None:
            return
        fin = tk.simpledialog.askfloat(
            "Nueva partición — Fin (MB)",
            f"Fin (MB, {inicio:.0f}-{disco_mb:.0f}):",
            minvalue=inicio + 1, maxvalue=disco_mb,
        )
        if fin is None:
            return
        fs = tk.simpledialog.askstring(
            "Sistema de archivos",
            "fat32 / exfat / ntfs / ext4 / linux-swap:",
            initialvalue="fat32",
        )
        if not fs:
            return
        from sectorzero.core.simulacion import simular_crear_particion
        from sectorzero.gui.ventana_simulacion import VentanaSimulacion
        sim = simular_crear_particion(
            self._resultado_actual, inicio, fin, fs.lower())
        VentanaSimulacion(self, sim, on_confirmar=self._ejecutar_operacion)

    def _op_eliminar(self):
        if not self._particion_seleccionada or self._particion_seleccionada.es_libre:
            self._log.escribir("Selecciona primero una partición.", "aviso")
            return
        from sectorzero.core.simulacion import simular_eliminar_particion
        from sectorzero.gui.ventana_simulacion import VentanaSimulacion
        sim = simular_eliminar_particion(
            self._resultado_actual, self._particion_seleccionada.numero)
        VentanaSimulacion(self, sim, on_confirmar=self._ejecutar_operacion)

    def _op_flag(self):
        if not self._particion_seleccionada or self._particion_seleccionada.es_libre:
            self._log.escribir("Selecciona primero una partición.", "aviso")
            return
        p = self._particion_seleccionada
        flag = tk.simpledialog.askstring(
            "Flag", "boot / lba / esp / hidden:", initialvalue="boot")
        if not flag:
            return
        activar = messagebox.askyesno(
            "Flag", f"¿Activar '{flag}' en #{p.numero}?\n(No = desactivar)")
        from sectorzero.core.simulacion import simular_cambiar_flag
        from sectorzero.gui.ventana_simulacion import VentanaSimulacion
        sim = simular_cambiar_flag(
            self._resultado_actual, p.numero, flag.lower(), activar)
        VentanaSimulacion(self, sim, on_confirmar=self._ejecutar_operacion)

    def _op_reparar_mbr(self):
        if not self._disco_actual:
            return
        if not messagebox.askyesno(
            "Reparar MBR",
            f"Restaurar firma 0x55AA en sector 0 de {self._disco_actual}.\n"
            f"No toca datos ni particiones, solo el sector de arranque.\n\n¿Confirmas?"
        ):
            return
        if not messagebox.askyesno(
            "Segunda confirmación",
            "¿Ejecutar definitivamente la reparación del MBR?"
        ):
            return
        self._log.escribir("Restaurando firma MBR (0x55AA)...", "aviso")
        cmd = f"dd if=/dev/zero of={self._disco_actual} bs=1 count=2 seek=510 conv=notrunc && printf '\\x55\\xAA' | dd of={self._disco_actual} bs=1 seek=510 conv=notrunc"
        self._lanzar_worker(self._worker_op_bash, cmd)

    def _ejecutar_operacion(self, sim):
        """Callback que recibe la simulación confirmada y ejecuta el comando real."""
        from sectorzero.core.disco import leer_disco
        self._log.escribir(f"Ejecutando: {sim.comando_parted}", "aviso")

        def _worker(cola):
            try:
                from sectorzero.core.wsl_utils import ejecutar_en_wsl
                partes = sim.comando_parted.split()
                proc = ejecutar_en_wsl(partes, distro=self._distro, timeout=30)
                salida = (proc.stdout + proc.stderr).strip()
                if proc.returncode == 0:
                    cola.put(_evento("operacion_ok",
                                      mensaje=f"✓ {sim.descripcion}"))
                else:
                    cola.put(_evento("operacion_error", mensaje=salida))
            except Exception as e:
                cola.put(_evento("operacion_error", mensaje=str(e)))

        self._lanzar_worker(_worker)

    def _worker_op_parted(self, cola, cmd_str):
        """Ejecuta un comando de parted y recarga el disco."""
        try:
            from sectorzero.core.wsl_utils import ejecutar_en_wsl
            partes = cmd_str.split()
            proc = ejecutar_en_wsl(partes, distro=self._distro, timeout=30)
            salida = (proc.stdout + proc.stderr).strip()
            if proc.returncode == 0:
                cola.put(_evento("operacion_ok", mensaje=f"OK — {cmd_str}"))
            else:
                cola.put(_evento("operacion_error", mensaje=salida))
        except Exception as e:
            cola.put(_evento("operacion_error", mensaje=str(e)))

    def _worker_op_bash(self, cola, cmd_str):
        """Ejecuta un comando bash arbitrario en WSL."""
        try:
            from sectorzero.core.wsl_utils import ejecutar_en_wsl
            proc = ejecutar_en_wsl(
                ["bash", "-c", cmd_str.replace("bash -c ", "")],
                distro=self._distro, timeout=30,
            )
            salida = (proc.stdout + proc.stderr).strip()
            if proc.returncode == 0:
                cola.put(_evento("operacion_ok", mensaje=f"OK — {salida or cmd_str}"))
            else:
                cola.put(_evento("operacion_error", mensaje=salida))
        except Exception as e:
            cola.put(_evento("operacion_error", mensaje=str(e)))


# ------------------------------------------------------------------
# Punto de entrada
# ------------------------------------------------------------------

def main():
    app = AppSectorZero()
    app.mainloop()


if __name__ == "__main__":
    main()
