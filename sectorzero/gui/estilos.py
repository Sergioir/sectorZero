"""
estilos.py — SectorZero
========================
Paleta visual de SectorZero. Misma familia que Disk Surgeon
(oscuro, JetBrains Mono) pero con acento azul en vez de verde
para distinguirlos claramente. El rojo sigue siendo zona de peligro.
"""

# Fondo
BG_OSCURO   = "#0d0d1a"
BG_PANEL    = "#13132b"
BG_ENTRADA  = "#0a0a1f"

# Acento principal — azul eléctrico (distinto del verde de DiskSurgeon)
AZUL_ELEC   = "#4FC3F7"   # acento principal SectorZero
AZUL_CLARO  = "#81D4FA"   # textos destacados
AZUL_DIM    = "#0d47a1"   # fondos de acento

# Colores funcionales
VERDE       = "#7CFFB2"   # OK, éxito
ROJO        = "#FF6B6B"   # error, peligro, destructivo
AMARILLO    = "#FFD93D"   # aviso, atención
GRIS        = "#6b6b8a"   # texto secundario
BLANCO      = "#f0f0ff"   # texto principal
TEXTO       = "#d4d4e8"   # texto normal

# Colores de particiones en la barra visual
COLORES_FS = {
    "exfat":   "#4FC3F7",  # azul claro
    "ntfs":    "#7986CB",  # índigo
    "fat32":   "#4DB6AC",  # teal
    "vfat":    "#4DB6AC",
    "ext4":    "#81C784",  # verde
    "ext3":    "#AED581",
    "btrfs":   "#DCE775",  # lima
    "swap":    "#FF8A65",  # naranja
    "libre":   "#1a1a3e",  # oscuro — espacio libre
    "unknown": "#546E7A",  # gris azulado
    "":        "#546E7A",
}

# Tipografía
MONO    = ("JetBrains Mono", 10)
MONO_SM = ("JetBrains Mono", 9)
MONO_LG = ("JetBrains Mono", 12)
TITULO  = ("JetBrains Mono", 16, "bold")
NORMAL  = ("Segoe UI", 10)

# Espaciado
PAD  = 12
PAD_SM = 6
