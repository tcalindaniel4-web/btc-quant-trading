"""
Pilonul 1 (Macro) - STH-SOPR de la BGeometrics + Z-score pe 90 de zile.
Ca la MVRV: cache zilnic și păstrarea istoricului deja salvat (API-ul gratuit dă doar ultimii 4 ani).
"""
import sys
import requests
import pandas as pd
from cache_util import e_descarcat_azi
from cai import DATA_DIR, token_bgeometrics

FISIER = DATA_DIR / 'macro_sopr.csv'
FEREASTRA_Z = 90

print("Preluăm datele SOPR de la BGeometrics...")


def descarca_sopr():
    # Endpoint-ul corect e primul (fiecare încercare consumă din limita de 10 cereri/oră)
    token = token_bgeometrics()
    for url in (f"https://api.bitcoin-data.com/v1/sth-sopr?token={token}",
                f"https://api.bitcoin-data.com/v1/sopr?token={token}"):
        try:
            response = requests.get(url, timeout=30)
            if response.status_code == 200:
                print("✅ Conectat cu succes la API-ul BGeometrics!")
                df = pd.DataFrame(response.json()).rename(columns={'d': 'Data'})
                col = [c for c in df.columns if c not in ['Data', 'unixTs']][0]
                return df.rename(columns={col: 'STH_SOPR'})[['Data', 'STH_SOPR']]
            print(f"   [i] {url.split('?')[0]} -> HTTP {response.status_code}")
        except Exception:
            continue
    return None


def fetch_and_process_sopr():
    vechi = pd.read_csv(FISIER)[['Data', 'STH_SOPR']] if FISIER.exists() else pd.DataFrame(columns=['Data', 'STH_SOPR'])

    if e_descarcat_azi(FISIER):
        print(f"♻️ Cache: {FISIER.name} a fost deja descărcat azi. Sărim peste API (folosește --force pentru reîncărcare).")
        brut = vechi
    else:
        nou = descarca_sopr()
        if nou is None:
            print("❌ Eroare: Nu am putut descărca datele. Verifică dacă cheia API a fost activată din contul tău.")
            sys.exit(1)
        brut = pd.concat([vechi, nou])

    try:
        df = brut.copy()
        df['STH_SOPR'] = pd.to_numeric(df['STH_SOPR'])
        df['Data'] = pd.to_datetime(df['Data']).dt.strftime('%Y-%m-%d')
        df = df.drop_duplicates('Data', keep='last').sort_values('Data').reset_index(drop=True)

        # Z-score pe 90 de zile: deviațiile extreme de la medie (capitulare / euforie pe termen scurt)
        medie = df['STH_SOPR'].rolling(window=FEREASTRA_Z).mean()
        dev = df['STH_SOPR'].rolling(window=FEREASTRA_Z).std()
        df['Z_SOPR'] = (df['STH_SOPR'] - medie) / dev

        # Păstrăm și primele 89 de zile (fără Z) ca istoric brut pentru calculele viitoare
        df[['Data', 'STH_SOPR', 'Z_SOPR']].to_csv(FISIER, index=False)

        ultim = df.dropna().iloc[-1]
        print(f"Succes! Baza de date SOPR a fost generată ({len(df)} înregistrări, {df.iloc[0]['Data']} -> {ultim['Data']}).")
        print(f"Ultima valoare SOPR: {ultim['STH_SOPR']:.4f}")
        print(f"Ultimul Z-Score (SOPR): {ultim['Z_SOPR']:.3f} (pe {ultim['Data']})")
    except Exception as e:
        print(f"❌ A apărut o eroare la procesarea datelor: {e}")
        sys.exit(1)


if __name__ == "__main__":
    fetch_and_process_sopr()
