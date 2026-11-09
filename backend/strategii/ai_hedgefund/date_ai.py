"""
DATE pentru strategia AI Hedge Fund (separată de strategia SDCA).

Descarcă (API-uri publice Binance, fără cheie):
  - lumânări zilnice BTCUSDT din 2017 (OHLCV + volum taker-buy)  -> ai_hedgefund/data/btc_1d.csv
  - funding rate BTCUSDT perpetual din 2019 (medie zilnică)       -> ai_hedgefund/data/funding_1d.csv
Refolosește (dacă există) datele on-chain ale proiectului: backend/data/macro_mvrv_ajustat.csv, macro_sopr.csv.

Toate datele sunt în UTC (închiderea zilnică Binance = 00:00 UTC).
Rulare:  python backend/strategii/ai_hedgefund/date_ai.py
"""
import sys
import time
from pathlib import Path

import pandas as pd
import requests

DIR = Path(__file__).resolve().parent
DATA_DIR = DIR / 'data'
PROIECT_DATA = DIR.parent.parent / 'data'  # backend/data (datele pipeline-ului)

SPOT_KLINES = "https://api.binance.com/api/v3/klines"
SPOT_PRICE = "https://api.binance.com/api/v3/ticker/price"
FUT_FUNDING = "https://fapi.binance.com/fapi/v1/fundingRate"
START_MS = int(pd.Timestamp('2017-08-17', tz='UTC').timestamp() * 1000)


def _get(url, params):
    for incercare in range(3):
        try:
            r = requests.get(url, params=params, timeout=30)
            if r.status_code == 200:
                return r.json()
            print(f"   [i] {url} -> HTTP {r.status_code}")
        except requests.RequestException as e:
            print(f"   [i] {url} -> {e.__class__.__name__}")
        time.sleep(2 * (incercare + 1))
    raise ConnectionError(f"Nu am putut descărca {url}")


def descarca_klines(start_ms=START_MS):
    randuri = []
    while True:
        data = _get(SPOT_KLINES, {"symbol": "BTCUSDT", "interval": "1d", "startTime": start_ms, "limit": 1000})
        if not data:
            break
        randuri.extend(data)
        start_ms = data[-1][0] + 1
        if len(data) < 1000:
            break
        time.sleep(0.3)
    df = pd.DataFrame(randuri, columns=['open_time', 'Open', 'High', 'Low', 'Close', 'Volume', 'close_time',
                                        'Quote_Volume', 'Trades', 'Taker_Buy_Base', 'Taker_Buy_Quote', '_'])
    df['Data'] = pd.to_datetime(df['open_time'], unit='ms', utc=True).dt.strftime('%Y-%m-%d')
    for c in ['Open', 'High', 'Low', 'Close', 'Volume', 'Quote_Volume', 'Taker_Buy_Base']:
        df[c] = df[c].astype(float)
    df['Trades'] = df['Trades'].astype(int)
    # Ultima lumânare e ziua curentă, încă deschisă: o marcăm ca să nu fie tratată drept închisă.
    acum_ms = int(time.time() * 1000)
    df['Inchisa'] = df['close_time'].astype('int64') < acum_ms
    cols = ['Data', 'Open', 'High', 'Low', 'Close', 'Volume', 'Quote_Volume', 'Trades', 'Taker_Buy_Base', 'Inchisa']
    return df[cols].drop_duplicates('Data', keep='last').reset_index(drop=True)


def descarca_funding():
    randuri, start_ms = [], int(pd.Timestamp('2019-09-01', tz='UTC').timestamp() * 1000)
    while True:
        data = _get(FUT_FUNDING, {"symbol": "BTCUSDT", "startTime": start_ms, "limit": 1000})
        if not data:
            break
        randuri.extend(data)
        start_ms = data[-1]['fundingTime'] + 1
        if len(data) < 1000:
            break
        time.sleep(0.3)
    df = pd.DataFrame(randuri)
    df['Data'] = pd.to_datetime(df['fundingTime'], unit='ms', utc=True).dt.strftime('%Y-%m-%d')
    df['Funding_Rate'] = df['fundingRate'].astype(float) * 100  # în procente / 8h
    return df.groupby('Data', as_index=False)['Funding_Rate'].mean()


def pret_curent():
    """Prețul spot BTCUSDT chiar acum (folosit de simulatorul live pentru stop-uri intraday)."""
    return float(_get(SPOT_PRICE, {"symbol": "BTCUSDT"})['price'])


def actualizeaza_tot():
    DATA_DIR.mkdir(exist_ok=True)
    print("⏳ Descarc lumânări zilnice BTCUSDT (2017 -> azi)...")
    k = descarca_klines()
    k.to_csv(DATA_DIR / 'btc_1d.csv', index=False)
    print(f"   ✅ {len(k)} zile ({k['Data'].iloc[0]} -> {k['Data'].iloc[-1]})")

    print("⏳ Descarc funding rate BTCUSDT perpetual (2019 -> azi)...")
    try:
        f = descarca_funding()
        f.to_csv(DATA_DIR / 'funding_1d.csv', index=False)
        print(f"   ✅ {len(f)} zile ({f['Data'].iloc[0]} -> {f['Data'].iloc[-1]})")
    except Exception as e:  # funding e doar filtru secundar: continuăm cu fișierul vechi
        print(f"   ⚠️ Funding indisponibil ({e}). Folosim ultimul fișier salvat, dacă există.")


def incarca_date():
    """Un singur DataFrame zilnic: preț + funding + on-chain (unde există)."""
    k = pd.read_csv(DATA_DIR / 'btc_1d.csv')
    df = k.copy()
    f_path = DATA_DIR / 'funding_1d.csv'
    if f_path.exists():
        df = df.merge(pd.read_csv(f_path), on='Data', how='left')
    else:
        df['Funding_Rate'] = float('nan')

    for fisier, col in (('macro_mvrv_ajustat.csv', 'Adjusted_MVRV'), ('macro_sopr.csv', 'STH_SOPR')):
        p = PROIECT_DATA / fisier
        if p.exists():
            m = pd.read_csv(p)[['Data', col]]
            m['Data'] = pd.to_datetime(m['Data']).dt.strftime('%Y-%m-%d')
            df = df.merge(m.drop_duplicates('Data'), on='Data', how='left')
            df[col] = df[col].ffill()  # on-chain vine cu câteva zile întârziere
        else:
            df[col] = float('nan')
    return df


if __name__ == "__main__":
    try:
        actualizeaza_tot()
    except Exception as e:
        print(f"❌ {e}")
        sys.exit(1)
