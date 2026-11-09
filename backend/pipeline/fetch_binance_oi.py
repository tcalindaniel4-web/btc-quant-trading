"""
Pilonul 2 (Derivate) - Funding Rate și Open Interest de la Binance Futures (API public).

Funding: istoric complet de la 2022-06 (paginat) -> intră în Master_Index.
Open Interest: Binance oferă doar ~30 de zile de istoric, deci nu poate fi testat în backtest;
îl păstrăm ca informație, dar NU mai intră în Master_Index (vezi merge_master.py).
Toate datele sunt în UTC.
"""
import sys
import requests
import pandas as pd
from cai import DATA_DIR

URL_OI = "https://fapi.binance.com/futures/data/openInterestHist"
URL_FUNDING = "https://fapi.binance.com/fapi/v1/fundingRate"
START = '2022-06-01'
FEREASTRA = 90

print("Preluăm Funding Rate și Open Interest de la Binance Futures...")


def _zi_utc(ms):
    return pd.to_datetime(ms, unit='ms', utc=True).strftime('%Y-%m-%d')


def descarca_funding():
    start_ms, toate = int(pd.Timestamp(START, tz='UTC').timestamp() * 1000), []
    while True:
        data = requests.get(URL_FUNDING, params={"symbol": "BTCUSDT", "startTime": start_ms, "limit": 1000}, timeout=30).json()
        if not isinstance(data, list):
            raise ValueError(f"Eroare neașteptată Funding: {data}")
        toate.extend(data)
        if len(data) < 1000:
            break
        start_ms = data[-1]['fundingTime'] + 1
    df = pd.DataFrame({'Data': [_zi_utc(p['fundingTime']) for p in toate],
                       'Funding_Rate': [float(p['fundingRate']) * 100 for p in toate]})
    return df.groupby('Data', as_index=False)['Funding_Rate'].mean()


def descarca_oi():
    data = requests.get(URL_OI, params={"symbol": "BTCUSDT", "period": "1d", "limit": 500}, timeout=30).json()
    if not isinstance(data, list):
        raise ValueError(f"Eroare neașteptată OI: {data}")
    df = pd.DataFrame({'Data': [_zi_utc(p['timestamp']) for p in data],
                       'Open_Interest': [float(p['sumOpenInterestValue']) for p in data]})
    return df.drop_duplicates('Data', keep='last')


def zscore(s, fereastra=FEREASTRA):
    return (s - s.rolling(fereastra, min_periods=7).mean()) / s.rolling(fereastra, min_periods=7).std()


def fetch_and_process_derivatives():
    try:
        df = descarca_funding()
        print(f"-> Funding: {len(df)} zile ({df.iloc[0]['Data']} -> {df.iloc[-1]['Data']}).")
        try:
            oi = descarca_oi()
            df = df.merge(oi, on='Data', how='left')
            print(f"-> Open Interest: {len(oi)} zile (doar informativ).")
        except Exception as e:
            print(f"   ⚠️ Open Interest indisponibil ({e}); continuăm doar cu funding.")
            df['Open_Interest'] = float('nan')

        df = df.sort_values('Data').reset_index(drop=True)
        df['Z_Funding_Rate'] = zscore(df['Funding_Rate'])
        df['Z_Open_Interest'] = zscore(df['Open_Interest'])

        df_final = df[['Data', 'Open_Interest', 'Z_Open_Interest', 'Funding_Rate', 'Z_Funding_Rate']]
        df_final = df_final[df_final['Z_Funding_Rate'].notna()]
        if len(df_final) == 0:
            print("❌ Eroare: Tabelul a rămas gol după procesarea statistică.")
            sys.exit(1)
        df_final.to_csv(DATA_DIR / 'binance_derivatives.csv', index=False)

        ultim = df_final.iloc[-1]
        print(f"✅ Succes! Datele futures au fost salvate ({len(df_final)} zile).")
        print(f"Ultimul Z-Score (Funding Rate): {ultim['Z_Funding_Rate']:.3f}")
        if pd.notna(ultim['Z_Open_Interest']):
            print(f"Ultimul Z-Score (Open Interest, informativ): {ultim['Z_Open_Interest']:.3f}")
    except Exception as e:
        print(f"❌ A apărut o eroare tehnică la execuție: {e}")
        sys.exit(1)


if __name__ == "__main__":
    fetch_and_process_derivatives()
