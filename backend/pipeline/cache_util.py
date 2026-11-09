import os
import sys
from datetime import datetime


def e_descarcat_azi(cale):
    """
    True dacă fișierul există și a fost scris azi (dată calendaristică locală).
    Datele on-chain (MVRV, SOPR) se schimbă o dată pe zi, așa că nu are rost
    să le cerem din nou la fiecare ciclu de 3 ore al botului (economisim limita tokenului).
    Forțezi o descărcare nouă rulând scriptul cu argumentul --force.
    """
    if '--force' in sys.argv or not os.path.exists(cale):
        return False
    modificat = datetime.fromtimestamp(os.path.getmtime(cale)).date()
    return modificat == datetime.now().date()
