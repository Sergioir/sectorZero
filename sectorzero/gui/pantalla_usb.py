"""
pantalla_usb.py — SectorZero
==============================
Pantalla de conexión de dispositivos USB a WSL via usbipd.
Se muestra entre el setup y la pantalla principal.
Es opcional — el usuario puede saltarla si el disco ya está
conectado o si quiere trabajar con un disco interno.
"""

from __future__ import annotations

import queue
import subprocess
import threading
import tkinter as tk
from typing import Optional

from sectorzero.gui.estilos import (
    BG_OSCURO, BG_PANEL, BG_ENTRADA,
    AZUL_ELEC, AZUL_CLARO, VERDE, ROJO, AMARILLO, GRIS, BLANCO, TEXTO,
    MONO, MONO_SM, MONO_LG, NORMAL, PAD, PAD_SM,
)

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _evento(tipo, **datos):
    return {"tipo": tipo, **datos}


def worker_listar_usb(cola: queue.Queue, distro: Optional[str]):
    try:
        from sectorzero.core.usbipd_utils import listar_usb_para_gui
        resultado = listar_usb_para_gui(distro=distro)
        cola.put(_evento("usb_listado", resultado=resultado))
    except Exception as ex:
        cola.put(_evento("error", mensaje=str(ex)))


def worker_conectar_usb(cola: queue.Queue, busid: str,
                         vidpid: str, distro: Optional[str]):
    try:
        import time
        from sectorzero.core.usbipd_utils import bind_y_attach, listar_usb_para_gui
        cola.put(_evento("log", texto=f"Conectando BUSID {busid}...", nivel="gris"))
        exito, msg = bind_y_attach(busid, distro=distro, vidpid=vidpid)
        cola.put(_evento("log",
                          texto=f"{'✓' if exito else '✗'} {msg}",
                          nivel="ok" if exito else "error"))
        time.sleep(2)
        resultado = listar_usb_para_gui(distro=distro)
        cola.put(_evento("usb_conectado", exito=exito, resultado=resultado, busid=busid))
    except Exception as ex:
        cola.put(_evento("error", mensaje=str(ex)))


def worker_desconectar_usb(cola: queue.Queue, busid: str):
    try:
        from sectorzero.core.usbipd_utils import detach
        exito, msg = detach(busid)
        cola.put(_evento("log",
                          texto=f"{'✓ Desconectado' if exito else '✗ Error'}: {msg}",
                          nivel="ok" if exito else "error"))
        cola.put(_evento("usb_desconectado", busid=busid))
    except Exception as ex:
        cola.put(_evento("error", mensaje=str(ex)))


class PantallaUSB(tk.Frame):
    """
    Pantalla de gestión de conexión USB.
    Muestra la tabla de dispositivos usbipd con botones de connect/disconnect.
    """

    def __init__(self, parent, on_continuar=None,
                 distro: Optional[str] = None, **kwargs):
        tk.Frame.__init__(self, parent, bg=BG_OSCURO, **kwargs)
        self._on_continuar = on_continuar
        self._distro = distro
        self._cola: queue.Queue = queue.Queue()
        self._activa = True
        self._filas_widgets = {}  # busid → frame de fila
        self._construir()
        self._procesar_cola()
        self._actualizar_lista()

    def _procesar_cola(self):
        try:
            while True:
                ev = self._cola.get_nowait()
                self._on_evento(ev)
        except Exception:
            pass
        finally:
            if self._activa:
                self.after(50, self._procesar_cola)

    def _lanzar_worker(self, fn, *args):
        threading.Thread(target=fn, args=(self._cola, *args), daemon=True).start()

    def _on_evento(self, ev):
        tipo = ev.get("tipo")
        if tipo == "usb_listado":
            self._mostrar_tabla(ev["resultado"])
        elif tipo == "usb_conectado":
            self._mostrar_tabla(ev["resultado"])
        elif tipo == "usb_desconectado":
            self._actualizar_lista()
        elif tipo == "log":
            self._log.escribir(ev.get("texto", ""), ev.get("nivel", "gris"))
        elif tipo == "error":
            self._log.escribir(f"Error: {ev['mensaje']}", "error")

    def _construir(self):
        # Cabecera
        cab = tk.Frame(self, bg=BG_PANEL)
        cab.pack(fill=tk.X)
        tk.Label(cab, text="◈ SECTOR ZERO  —  Conectar dispositivo USB",
                  bg=BG_PANEL, fg=AZUL_ELEC, font=MONO_LG).pack(
            side=tk.LEFT, padx=PAD, pady=PAD_SM)

        # Descripción
        tk.Label(self,
                  text="Conecta el disco USB a WSL para que SectorZero pueda acceder a él.\n"
                       "Si el disco ya está conectado o vas a trabajar con un disco interno, pulsa Continuar.",
                  bg=BG_OSCURO, fg=GRIS, font=MONO_SM,
                  justify=tk.LEFT).pack(anchor="w", padx=PAD, pady=(PAD_SM, 0))

        # Cabecera de tabla
        frame_cab = tk.Frame(self, bg=BG_PANEL)
        frame_cab.pack(fill=tk.X, padx=PAD, pady=(PAD, 0))

        for texto, ancho in [("BUSID", 8), ("Dispositivo", 36),
                               ("Tamaño", 10), ("Estado", 22), ("", 18)]:
            tk.Label(frame_cab, text=texto, bg=BG_PANEL,
                      fg=AZUL_ELEC, font=MONO_SM, width=ancho, anchor="w").pack(
                side=tk.LEFT, padx=4, pady=4)

        # Área de tabla (scrollable)
        frame_scroll = tk.Frame(self, bg=BG_OSCURO)
        frame_scroll.pack(fill=tk.BOTH, expand=True, padx=PAD)

        canvas = tk.Canvas(frame_scroll, bg=BG_OSCURO, highlightthickness=0)
        sb = tk.Scrollbar(frame_scroll, orient="vertical", command=canvas.yview)
        self._frame_filas = tk.Frame(canvas, bg=BG_OSCURO)
        self._frame_filas.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=self._frame_filas, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Log
        tk.Label(self, text="Log", bg=BG_OSCURO, fg=GRIS,
                  font=MONO_SM).pack(anchor="w", padx=PAD, pady=(PAD_SM, 0))
        self._log = _AreaLogSimple(self, alto=80)
        self._log.pack(fill=tk.X, padx=PAD, pady=(0, PAD_SM))

        # Pie
        pie = tk.Frame(self, bg=BG_PANEL, height=52)
        pie.pack(fill=tk.X, side=tk.BOTTOM)
        pie.pack_propagate(False)

        from sectorzero.gui.app import BotonSZ
        BotonSZ(pie, "↺ Actualizar",
                 comando=self._actualizar_lista,
                 color=AMARILLO, ancho=130).pack(side=tk.LEFT, padx=PAD_SM, pady=PAD_SM)

        BotonSZ(pie, "Continuar →",
                 comando=self._continuar,
                 color=AZUL_ELEC, ancho=160).pack(side=tk.RIGHT, padx=PAD_SM, pady=PAD_SM)

    def _actualizar_lista(self):
        self._log.escribir("Actualizando lista de dispositivos USB...", "gris")
        self._lanzar_worker(worker_listar_usb, self._distro)

    def _mostrar_tabla(self, resultado):
        for w in self._frame_filas.winfo_children():
            w.destroy()
        self._filas_widgets.clear()

        if not resultado.ejecucion_correcta:
            tk.Label(self._frame_filas,
                      text=f"Error: {resultado.error}",
                      bg=BG_OSCURO, fg=ROJO, font=MONO_SM).pack(
                anchor="w", padx=PAD_SM, pady=PAD_SM)
            return

        solo_alm = [d for d in resultado.dispositivos_usbipd if d.es_almacenamiento]

        if not solo_alm:
            tk.Label(self._frame_filas,
                      text="No se detectaron dispositivos de almacenamiento USB.",
                      bg=BG_OSCURO, fg=GRIS, font=MONO_SM).pack(
                anchor="w", padx=PAD_SM, pady=PAD_SM)
            return

        mapa_size = {usb.busid: disco.size for usb, disco in resultado.cruces}
        info_win = resultado.info_windows or {}

        for i, dev in enumerate(solo_alm):
            bg = BG_OSCURO if i % 2 == 0 else BG_PANEL
            fila = tk.Frame(self._frame_filas, bg=bg)
            fila.pack(fill=tk.X)
            self._filas_widgets[dev.busid] = fila

            size = mapa_size.get(dev.busid, "—")

            # Nombre real de Windows via VID:PID
            vidpid = dev.vidpid.lower()
            disco_win = info_win.get(vidpid, {})
            nombre = (disco_win.get("FriendlyName") or dev.nombre)[:36]

            color_estado = (VERDE if dev.adjunto_a_wsl
                             else AMARILLO if dev.necesita_attach
                             else GRIS)

            for texto, ancho in [
                (dev.busid, 8), (nombre, 36),
                (size, 10), (dev.estado_legible, 22),
            ]:
                tk.Label(fila, text=texto, bg=bg, fg=TEXTO,
                          font=MONO_SM, width=ancho, anchor="w").pack(
                    side=tk.LEFT, padx=4, pady=3)

            # Botón según estado
            from sectorzero.gui.app import BotonSZ
            if dev.adjunto_a_wsl:
                tk.Label(fila, text="✓ En WSL", bg=bg,
                          fg=VERDE, font=MONO_SM, width=18).pack(side=tk.LEFT, padx=4)
            elif dev.necesita_attach:
                def _conectar(busid=dev.busid, vp=dev.vidpid):
                    self._lanzar_worker(worker_conectar_usb, busid, vp, self._distro)
                BotonSZ(fila, "Conectar a WSL",
                         comando=_conectar,
                         color=AMARILLO, ancho=150).pack(side=tk.LEFT, padx=4, pady=2)
            else:
                def _bind_conectar(busid=dev.busid, vp=dev.vidpid):
                    self._lanzar_worker(worker_conectar_usb, busid, vp, self._distro)
                BotonSZ(fila, "Registrar y conectar",
                         comando=_bind_conectar,
                         color=GRIS, ancho=160).pack(side=tk.LEFT, padx=4, pady=2)

    def _continuar(self):
        self._activa = False
        if self._on_continuar:
            self._on_continuar()


class _AreaLogSimple(tk.Frame):
    """Log simplificado sin dependencias externas."""
    COLORES = {"ok": VERDE, "error": ROJO, "aviso": AMARILLO,
                "gris": GRIS, "info": AZUL_CLARO}

    def __init__(self, parent, alto=80, **kwargs):
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
