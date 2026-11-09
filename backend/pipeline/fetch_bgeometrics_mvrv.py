"""
Pilonul 1 (Macro) - MVRV de la BGeometrics + MVRV ajustat (benzi dinamice curbate).

Limite plan gratuit BGeometrics: ultimii 4 ani de istoric, 10 cereri / oră, ultimele 7 zile ascunse.
De aceea: descărcăm cel mult o dată pe zi (cache) și PĂSTRĂM istoricul deja salvat
(API-ul "uită" zilele mai vechi de 4 ani; fișierul nostru nu).
"""
import sys
import requests
import pandas as pd
import numpy as np
from cache_util import e_descarcat_azi
from cai import DATA_DIR, token_bgeometrics

FISIER = DATA_DIR / 'macro_mvrv_ajustat.csv'

# Benzile sunt funcții de "numărul zilei" (bar_index din formula originală, numărat de la
# începutul graficului BTC). ORIGINE FIXĂ: înainte, numărătoarea pornea de la primul rând primit
# de la API, iar fereastra de 4 ani a API-ului mută acel rând zilnic -> benzile "alunecau".
ORIGINE_BENZI = pd.Timestamp('2010-07-18')

print("Preluăm datele MVRV live de la BGeometrics...")


def descarca_mvrv():
    token = token_bgeometrics()
    for url in (f"https://api.bitcoin-data.com/v1/mvrv?token={token}",
                f"https://api.bitcoin-data.com/v1/mvrv?api_key={token}"):
        try:
            response = requests.get(url, timeout=30)
            if response.status_code == 200:
                print("✅ Conectat cu succes la API-ul BGeometrics pentru MVRV!")
                df = pd.DataFrame(response.json()).rename(columns={'d': 'Data'})
                col = [c for c in df.columns if c not in ['Data', 'unixTs']][0]
                return df.rename(columns={col: 'MVRV'})[['Data', 'MVRV']]
            print(f"   [i] {url.split('?')[0]} -> HTTP {response.status_code}")
        except Exception:
            continue
    return None


def ajusteaza(df):
    """MVRV ajustat: poziția lui log2(MVRV) între banda oversold și overbought, ridicată la 1.5."""
    df = df.copy()
    df['MVRV'] = pd.to_numeric(df['MVRV'])
    df['Data'] = pd.to_datetime(df['Data']).dt.strftime('%Y-%m-%d')
    df = df.drop_duplicates('Data', keep='last').sort_values('Data').reset_index(drop=True)
    zi = (pd.to_datetime(df['Data']) - ORIGINE_BENZI).dt.days + 1
    df['oversold'] = np.log(zi + 2500) - 9.35
    df['overbought'] = -np.log(zi + 2000) + 10.75
    raport = (np.log2(df['MVRV']) - df['oversold']) / (df['overbought'] - df['oversold'])
    df['Adjusted_MVRV'] = np.where(raport >= 0, raport ** 1.5, -(np.abs(raport) ** 1.5))
    return df[['Data', 'MVRV', 'oversold', 'overbought', 'Adjusted_MVRV']].dropna()


def fetch_and_process_mvrv():
    vechi = pd.read_csv(FISIER)[['Data', 'MVRV']] if FISIER.exists() else pd.DataFrame(columns=['Data', 'MVRV'])

    if e_descarcat_azi(FISIER):
        print(f"♻️ Cache: {FISIER.name} a fost deja descărcat azi. Sărim peste API (folosește --force pentru reîncărcare).")
        brut = vechi
    else:
        nou = descarca_mvrv()
        if nou is None:
            print("❌ Eroare: Nu am putut descărca datele MVRV de la BGeometrics.")
            sys.exit(1)
        brut = pd.concat([vechi, nou])  # păstrăm istoricul vechi, datele noi au prioritate

    try:
        df_final = ajusteaza(brut)
        df_final.to_csv(FISIER, index=False)
        print(f"Succes! Baza de date MVRV a fost actualizată și ajustată ({len(df_final)} înregistrări, "
              f"{df_final.iloc[0]['Data']} -> {df_final.iloc[-1]['Data']}).")
        print(f"Ultimul scor Adjusted MVRV: {df_final.iloc[-1]['Adjusted_MVRV']:.3f} (pe {df_final.iloc[-1]['Data']})")
    except Exception as e:
        print(f"❌ A apărut o eroare la procesarea datelor: {e}")
        sys.exit(1)


if __name__ == "__main__":
    fetch_and_process_mvrv()
