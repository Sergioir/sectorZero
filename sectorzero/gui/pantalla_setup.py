"""
pantalla_setup.py — SectorZero
================================
Pantalla de verificación e instalación de dependencias.
Mismo patrón que Disk Surgeon: muestra el comando antes de ejecutarlo,
abre PowerShell para que el usuario vea qué pasa.
"""

from __future__ import annotations

import platform
import queue
import subprocess
import tkinter as tk

from sectorzero.gui.estilos import (
    BG_OSCURO, BG_PANEL, BG_ENTRADA,
    AZUL_ELEC, AZUL_CLARO, VERDE, ROJO, AMARILLO, GRIS, BLANCO, TEXTO,
    MONO, MONO_SM, MONO_LG, NORMAL, PAD, PAD_SM,
)
from sectorzero.gui.instalacion import (
    PasoInstalacion, TipoEjecucion, PASOS,
    verificar_todos, pasos_aplicables,
)

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


# ------------------------------------------------------------------
# Funciones de ejecución de comandos
# ------------------------------------------------------------------

def _ejecutar_en_powershell_admin(comando: str):
    if platform.system() != "Windows":
        return
    try:
        import ctypes
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", "powershell.exe",
            f'-NoExit -Command "{comando}"', None, 1,
        )
    except Exception as e:
        import tkinter.messagebox as mb
        mb.showerror("Error UAC", str(e))


def _ejecutar_en_powershell_normal(comando: str):
    if platform.system() != "Windows":
        return
    subprocess.Popen(
        ["powershell.exe", "-NoExit", "-Command", comando],
        creationflags=subprocess.CREATE_NEW_CONSOLE,
    )


def _abrir_url(url: str):
    import webbrowser
    webbrowser.open(url)


# ------------------------------------------------------------------
# Worker de verificación
# ------------------------------------------------------------------

def worker_verificar(cola: queue.Queue):
    pasos = pasos_aplicables()
    for paso in pasos:
        cola.put({"tipo": "verificando", "id": paso.id})
    estados = verificar_todos()
    for id_paso, ok in estados.items():
        cola.put({"tipo": "estado", "id": id_paso, "ok": ok})
    todo_ok = all(
        estados.get(p.id, True)
        for p in pasos
        if not p.opcional
    )
    cola.put({"tipo": "completo", "todo_ok": todo_ok})


# ------------------------------------------------------------------
# Widget de fila de paso
# ------------------------------------------------------------------

class FilaPaso(tk.Frame):

    def __init__(self, parent, paso: PasoInstalacion, on_ejecutado=None, **kwargs):
        super().__init__(parent, bg=BG_PANEL, **kwargs)
        self.paso = paso
        self._on_ejecutado = on_ejecutado
        self._instalado = None
        self._expandido = False
        self._frame_detalle = None
        self._construir_cabecera()

    def _construir_cabecera(self):
        cab = tk.Frame(self, bg=BG_PANEL, cursor="hand2")
        cab.pack(fill=tk.X, padx=PAD_SM, pady=2)
        cab.bind("<Button-1>", self._toggle)

        self._lbl_icono = tk.Label(cab, text="…", bg=BG_PANEL,
                                    fg=GRIS, font=MONO, width=3)
        self._lbl_icono.pack(side=tk.LEFT)
        self._lbl_icono.bind("<Button-1>", self._toggle)

        tk.Label(cab, text=self.paso.nombre, bg=BG_PANEL,
                  fg=BLANCO, font=MONO, anchor="w").pack(
            side=tk.LEFT, padx=PAD_SM, expand=True, fill=tk.X)

        tk.Label(cab, text=self.paso.descripcion_corta, bg=BG_PANEL,
                  fg=GRIS, font=MONO_SM, anchor="e").pack(side=tk.RIGHT, padx=PAD_SM)

        self._lbl_toggle = tk.Label(cab, text="▸", bg=BG_PANEL,
                                     fg=GRIS, font=MONO, width=2)
        self._lbl_toggle.pack(side=tk.RIGHT)
        self._lbl_toggle.bind("<Button-1>", self._toggle)

    def _toggle(self, e=None):
        if self._expandido:
            self._contraer()
        else:
            self._expandir()

    def _expandir(self):
        self._expandido = True
        self._lbl_toggle.config(text="▾")
        if self._frame_detalle:
            self._frame_detalle.destroy()
        self._frame_detalle = tk.Frame(self, bg=BG_ENTRADA)
        self._frame_detalle.pack(fill=tk.X, padx=PAD, pady=(0, PAD_SM))
        self._construir_detalle(self._frame_detalle)

    def _contraer(self):
        self._expandido = False
        self._lbl_toggle.config(text="▸")
        if self._frame_detalle:
            self._frame_detalle.destroy()
            self._frame_detalle = None

    def _construir_detalle(self, parent):
        tk.Label(parent, text=self.paso.descripcion_larga,
                  bg=BG_ENTRADA, fg=TEXTO, font=NORMAL,
                  wraplength=680, justify=tk.LEFT, anchor="w").pack(
            fill=tk.X, padx=PAD_SM, pady=PAD_SM)

        if self._instalado:
            tk.Label(parent, text="✓ Ya instalado",
                      bg=BG_ENTRADA, fg=VERDE, font=MONO).pack(
                padx=PAD_SM, pady=PAD_SM)
            return

        # Caja del comando
        frame_cmd = tk.Frame(parent, bg=BG_OSCURO)
        frame_cmd.pack(fill=tk.X, padx=PAD_SM, pady=(0, PAD_SM))

        tk.Label(frame_cmd, text="Comando:",
                  bg=BG_OSCURO, fg=GRIS, font=MONO_SM).pack(
            anchor="w", padx=PAD_SM, pady=(PAD_SM, 0))

        caja = tk.Text(frame_cmd, height=2, bg=BG_PANEL, fg=AZUL_ELEC,
                        font=MONO, relief=tk.FLAT, padx=8, pady=4,
                        wrap=tk.WORD, state=tk.NORMAL)
        caja.insert("1.0", self.paso.comando)
        caja.configure(state=tk.DISABLED)
        caja.pack(fill=tk.X, padx=PAD_SM, pady=(0, PAD_SM))

        if self.paso.advertencia:
            tk.Label(frame_cmd, text=f"⚠ {self.paso.advertencia}",
                      bg=BG_OSCURO, fg=AMARILLO, font=MONO_SM,
                      wraplength=660, justify=tk.LEFT).pack(
                fill=tk.X, padx=PAD_SM, pady=(0, PAD_SM))

        if self.paso.requiere_reinicio:
            tk.Label(frame_cmd, text="⟳ Requiere reiniciar Windows.",
                      bg=BG_OSCURO, fg=AMARILLO, font=MONO_SM).pack(
                anchor="w", padx=PAD_SM, pady=(0, PAD_SM))

        # Botón de ejecución
        from sectorzero.gui.app import BotonSZ
        texto_btn = ("▶ Ejecutar en PowerShell (admin)"
                      if self.paso.tipo_ejecucion == TipoEjecucion.POWERSHELL_ADMIN
                      else "▶ Ejecutar en PowerShell")
        BotonSZ(parent, texto_btn, comando=self._ejecutar,
                 color=AZUL_ELEC, ancho=260).pack(padx=PAD_SM, pady=PAD_SM)

    def _ejecutar(self):
        tipo = self.paso.tipo_ejecucion
        if tipo == TipoEjecucion.POWERSHELL_ADMIN:
            _ejecutar_en_powershell_admin(self.paso.comando)
        elif tipo in (TipoEjecucion.POWERSHELL_NORMAL, TipoEjecucion.WSL):
            _ejecutar_en_powershell_normal(self.paso.comando)
        if self._on_ejecutado:
            self._on_ejecutado(self.paso.id)

    def actualizar_estado(self, ok: bool):
        self._instalado = ok
        if ok:
            self._lbl_icono.config(text="✓", fg=VERDE)
        else:
            color = GRIS if self.paso.opcional else ROJO
            self._lbl_icono.config(text="✗", fg=color)
        if self._expandido and self._frame_detalle:
            self._frame_detalle.destroy()
            self._frame_detalle = tk.Frame(self, bg=BG_ENTRADA)
            self._frame_detalle.pack(fill=tk.X, padx=PAD, pady=(0, PAD_SM))
            self._construir_detalle(self._frame_detalle)


# ------------------------------------------------------------------
# Pantalla completa de setup
# ------------------------------------------------------------------

class PantallaSetup(tk.Frame):

    def __init__(self, parent, on_completo=None, **kwargs):
        tk.Frame.__init__(self, parent, bg=BG_OSCURO, **kwargs)
        self._on_completo = on_completo
        self._cola: queue.Queue = queue.Queue()
        self._filas: dict[str, FilaPaso] = {}
        self._activa = True
        self._construir()
        self._verificar()
        self._procesar_cola()

    def _procesar_cola(self):
        try:
            while True:
                ev = self._cola.get_nowait()
                tipo = ev.get("tipo")
                if tipo == "verificando":
                    if ev["id"] in self._filas:
                        self._filas[ev["id"]]._lbl_icono.config(text="…", fg=GRIS)
                elif tipo == "estado":
                    if ev["id"] in self._filas:
                        self._filas[ev["id"]].actualizar_estado(ev["ok"])
                elif tipo == "completo":
                    if ev.get("todo_ok"):
                        self._lbl_estado.config(text="Todo listo ✓", fg=VERDE)
                        self._btn_continuar.activar()
                    else:
                        faltantes = sum(
                            1 for p in pasos_aplicables()
                            if not p.opcional
                            and self._filas.get(p.id)
                            and self._filas[p.id]._instalado is False
                        )
                        self._lbl_estado.config(
                            text=f"Faltan {faltantes} herramienta(s) obligatoria(s)",
                            fg=AMARILLO)
                        self._btn_continuar.activar()
        except Exception:
            pass
        finally:
            if self._activa:
                self.after(50, self._procesar_cola)

    def _construir(self):
        tk.Label(self, text="Configuración inicial",
                  bg=BG_OSCURO, fg=AZUL_ELEC, font=MONO_LG).pack(
            pady=(PAD, PAD_SM), anchor="w", padx=PAD)

        tk.Label(self,
                  text="SectorZero necesita WSL2 con Kali Linux y las herramientas de particiones.\n"
                       "Pulsa en cada elemento para ver qué hace y ejecutar su instalación.",
                  bg=BG_OSCURO, fg=GRIS, font=MONO_SM,
                  wraplength=760, justify=tk.LEFT).pack(
            pady=(0, PAD), anchor="w", padx=PAD)

        # Lista con scroll
        frame_scroll = tk.Frame(self, bg=BG_OSCURO)
        frame_scroll.pack(fill=tk.BOTH, expand=True, padx=PAD)

        canvas = tk.Canvas(frame_scroll, bg=BG_OSCURO, highlightthickness=0)
        scrollbar = tk.Scrollbar(frame_scroll, orient="vertical", command=canvas.yview)
        self._frame_pasos = tk.Frame(canvas, bg=BG_OSCURO)
        self._frame_pasos.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=self._frame_pasos, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        for paso in pasos_aplicables():
            sep = tk.Frame(self._frame_pasos, bg=BG_OSCURO, height=2)
            sep.pack(fill=tk.X)
            fila = FilaPaso(self._frame_pasos, paso,
                             on_ejecutado=self._on_paso_ejecutado)
            fila.pack(fill=tk.X)
            self._filas[paso.id] = fila

        # Pie
        pie = tk.Frame(self, bg=BG_PANEL, height=52)
        pie.pack(fill=tk.X, side=tk.BOTTOM)
        pie.pack_propagate(False)

        self._lbl_estado = tk.Label(pie, text="Verificando...",
                                     bg=BG_PANEL, fg=GRIS, font=MONO_SM)
        self._lbl_estado.pack(side=tk.LEFT, padx=PAD)

        from sectorzero.gui.app import BotonSZ
        self._btn_continuar = BotonSZ(pie, "Continuar →",
                                       comando=self._continuar,
                                       color=AZUL_ELEC, ancho=160)
        self._btn_continuar.pack(side=tk.RIGHT, padx=PAD_SM, pady=PAD_SM)
        self._btn_continuar.desactivar()

        BotonSZ(pie, "↺ Re-verificar",
                 comando=self._verificar,
                 color=AMARILLO, ancho=140).pack(side=tk.RIGHT, padx=PAD_SM, pady=PAD_SM)

    def _verificar(self):
        import threading
        self._lbl_estado.config(text="Verificando...", fg=GRIS)
        self._btn_continuar.desactivar()
        threading.Thread(target=worker_verificar, args=(self._cola,), daemon=True).start()

    def _on_paso_ejecutado(self, id_paso):
        self.after(3000, self._verificar)

    def _continuar(self):
        self._activa = False
        if self._on_completo:
            self._on_completo()
