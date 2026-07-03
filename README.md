# SectorZero

**Gestión y reparación de tablas de particiones con interfaz gráfica.**

> ⚠ **BETA** — Las operaciones de escritura no han sido validadas en producción todavía.
> Los discos internos están protegidos en modo solo lectura.
> Úsalo en pendrives y discos externos de prueba primero.

El nombre viene del `fdisk /mbr` de los años 2000 — el comando que limpiaba el sector 0
del disco y devolvía un sistema que no arrancaba. SectorZero hace lo mismo, con interfaz
gráfica, registro de cadena de custodia, y sin destruir nada sin doble confirmación.

---

## Descarga

→ [Última versión en Releases](../../releases/latest)

Descarga `SectorZero.exe` y ejecútalo. El asistente instala todo lo necesario.

---

## Qué hace

### Visualización (siempre disponible, cualquier disco)
- **Barra visual proporcional** del disco — cada partición como bloque coloreado según su FS
- **Tabla de particiones** completa: número, inicio, fin, tamaño, FS, nombre, flags
- **Estado del sector de arranque**: firma MBR 0x55AA, presencia de código de arranque
- Distingue automáticamente discos USB externos de discos internos del sistema

### Operaciones (solo en discos USB externos)
- Nueva tabla de particiones MBR o GPT
- Nueva partición con sistema de archivos, inicio y fin en MB
- Eliminar partición
- Cambiar flags (boot, esp, lba, hidden...)
- Reparar firma MBR (restaurar 0x55AA)

Todas las operaciones destructivas requieren doble confirmación y muestran el
comando exacto antes de ejecutarlo.

### Protecciones
- **Discos internos**: modo solo lectura automático — botones desactivados
- **Operaciones**: doble confirmación siempre
- **Cadena de custodia**: logs/chain.jsonl con tabla antes y después de cada operación

---

## Diferencia con Disk Surgeon

| | Disk Surgeon | SectorZero |
|---|---|---|
| Problema | FS corrupto dentro de la partición | Tabla de particiones dañada |
| Herramienta | fsck / ntfsfix | parted / gdisk |
| Caso típico | Pendrive que pide formatear | Disco que no aparece o no arranca |
| Riesgo | Bajo | Alto |

---

## Dependencias (el asistente las instala)

WSL2, Kali Linux, GNU parted, gdisk

---

## Requisitos

- Windows 10 v2004+ / Windows 11
- Conexión a internet la primera vez

---

## Desarrollo

```powershell
python sector_zero.py
```

---

## Hoja de ruta

- ✅ Visualización tabla MBR y GPT con barra proporcional
- ✅ Estado del sector de arranque
- ✅ Protección automática de discos internos
- ✅ Conexión USB via usbipd integrada
- ✅ Operaciones en USB: tabla, partición, eliminar, flags, reparar MBR
- 🔜 Validación en casos reales
- 🔜 Recuperación tabla GPT desde copia de respaldo
- 🔜 Acceso completo a discos internos (v1.0)
- 🔜 sectorzero.infodocencia.net

---

Parte del ecosistema [infodocencia.net](https://infodocencia.net) —
[Disk Surgeon](https://disksurgeon.infodocencia.net)

---

## ⚠ DISCLAIMER

```
THIS SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
EXPRESS OR IMPLIED. USE AT YOUR OWN RISK.

Partition table operations are IRREVERSIBLE. A mistake here can
render a disk completely unusable and cause permanent data loss.

The authors accept NO responsibility for:
- Data loss resulting from use of this software
- System failures caused by partition table modifications
- Any damage, direct or indirect, arising from use of SectorZero

By using this software you acknowledge that you understand these
risks and accept full responsibility for the consequences.

ALWAYS have a complete backup before making any changes.
```
