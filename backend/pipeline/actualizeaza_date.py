"""
ACTUALIZARE DATE (pipeline-ul celor 3 piloni + fuziune) -> backend/data/master_dataset.csv
Rulare: python backend/pipeline/actualizeaza_date.py   (o pornește automat și botul SDCA)
"""
import os
import subprocess
import time
import sys  # sys.executable forțează folosirea Python-ului din venv
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parent

print("="*50)
print("INIȚIALIZARE SISTEM DE TRANZACȚIONARE CANTITATIVĂ")
print("="*50)

# (nume, fișier, critic)
# critic=True  -> dacă pică, oprim pipeline-ul și ieșim cu cod 1 (botul nu va decide pe date vechi)
# critic=False -> dacă pică, continuăm cu ultimul fișier salvat (datele macro/derivate se schimbă lent)
scripturi = [
    ("Pilonul 1 (Macro - MVRV)", "fetch_bgeometrics_mvrv.py", False),
    ("Pilonul 1 (Macro - SOPR)", "fetch_bgeometrics_sopr.py", False),
    ("Pilonul 2 (Derivate)", "fetch_binance_oi.py", False),
    ("Pilonul 3 (Micro/Execuție - VWAP, MACD, RSI)", "fetch_price_vwap.py", True),
    ("Fuziune & Decizie (Master)", "merge_master.py", True),
]

esuate = []
for nume, fisier, critic in scripturi:
    print(f"\n⏳ Rulăm: {nume}...")
    try:
        # PYTHONIOENCODING: altfel pe Windows emoji-urile din print() pică în pipe (cp1252).
        rezultat = subprocess.run([sys.executable, str(PIPELINE_DIR / fisier)], capture_output=True, text=True,
                                  cwd=PIPELINE_DIR,
                                  encoding='utf-8', errors='replace', timeout=300,
                                  env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})
        if rezultat.stdout.strip():
            print(rezultat.stdout.strip())
        if rezultat.returncode != 0:
            if rezultat.stderr.strip():
                print(rezultat.stderr.strip())
            esuate.append(nume)
            if critic:
                print(f"❌ {fisier} a eșuat și este CRITIC. Oprim actualizarea.")
                sys.exit(1)
            print(f"⚠️ {fisier} a eșuat. Continuăm cu ultimele date salvate pentru acest pilon.")
    except subprocess.TimeoutExpired:
        esuate.append(nume)
        print(f"❌ {fisier} a depășit 5 minute.")
        if critic:
            sys.exit(1)

    time.sleep(1)  # Pauză scurtă pentru a nu supraîncărca API-urile

print("\n" + "-"*50)
if esuate:
    print(f"⚠️ Actualizare PARȚIALĂ. Piloni pe date vechi: {', '.join(esuate)}")
else:
    print("✅ Toate sursele de date au fost actualizate.")
