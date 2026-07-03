"""
sector_zero.py
==============
Punto de entrada de SectorZero.

Uso:
    python sector_zero.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sectorzero.gui.app import main

if __name__ == "__main__":
    main()
