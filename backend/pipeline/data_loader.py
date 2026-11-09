import pandas as pd
from cai import DATA_DIR

MASTER_PATH = DATA_DIR / 'master_dataset.csv'
COLOANE_NECESARE = ['Data', 'Open', 'High', 'Low', 'Close', 'Volume', 'Master_Index']


def incarca_dataset():
    """
    Încarcă backend/data/master_dataset.csv (generat de merge_master.py), care conține
    deja OHLCV + toți indicatorii. Înlocuiește vechea căutare automată a unui CSV
    de preț în data/, care alegea un fișier static și făcea botul să ruleze pe date înghețate.
    Returnează None (cu mesaj) dacă fișierul lipsește sau e incomplet.
    """
    if not MASTER_PATH.exists():
        print(f"[!] {MASTER_PATH.name} nu există. Rulează backend/pipeline/actualizeaza_date.py.")
        return None

    df = pd.read_csv(MASTER_PATH)
    lipsa = [c for c in COLOANE_NECESARE if c not in df.columns]
    if lipsa:
        print(f"[!] {MASTER_PATH.name} nu are coloanele {lipsa}. Rulează din nou backend/pipeline/actualizeaza_date.py.")
        return None

    df['Data'] = pd.to_datetime(df['Data']).dt.strftime('%Y-%m-%d')
    return df.sort_values('Data').reset_index(drop=True)
