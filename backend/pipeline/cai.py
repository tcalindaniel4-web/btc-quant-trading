"""Căi absolute comune + configurare secretă (.env): scripturile merg indiferent din ce folder sunt pornite."""
import os
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parent
BACKEND_DIR = PIPELINE_DIR.parent
PROIECT_DIR = BACKEND_DIR.parent
DATA_DIR = BACKEND_DIR / 'data'
DATA_DIR.mkdir(exist_ok=True)


def _incarca_env(cale=PROIECT_DIR / '.env'):
    """Citește perechile CHEIE=valoare din .env în variabilele de mediu (fără bibliotecă externă).
    O variabilă deja setată în sistem are prioritate față de fișier."""
    if not cale.exists():
        return
    for linie in cale.read_text(encoding='utf-8').splitlines():
        linie = linie.strip()
        if not linie or linie.startswith('#') or '=' not in linie:
            continue
        cheie, valoare = linie.split('=', 1)
        os.environ.setdefault(cheie.strip(), valoare.strip().strip('"').strip("'"))


_incarca_env()


def token_bgeometrics():
    """Tokenul API BGeometrics din .env (BGEOMETRICS_TOKEN). Nu se mai ține în cod."""
    token = os.environ.get('BGEOMETRICS_TOKEN', '').strip()
    if not token:
        raise RuntimeError("Lipsește BGEOMETRICS_TOKEN. Copiază .env.example în .env și pune tokenul tău "
                           "(din contul bitcoin-data.com).")
    return token
