"""
PANOU DE DERIVATE (în stilul Coinalyze), din API-ul public Binance Futures (BTCUSDT perpetual, fără cheie).

Serii aliniate pe același interval (15m / 1h / 4h):
  - prețul (închiderea lumânării futures)
  - Open Interest în USD                       (/futures/data/openInterestHist, ~30 zile de istoric)
  - CVD: delta cumulată a volumului agresiv     (taker buy - taker sell, în USD, din /futures/data/takerlongshortRatio)
  - raportul long/short al conturilor           (/futures/data/globalLongShortAccountRatio)
  - funding rate, la fiecare 8 ore              (/fapi/v1/fundingRate)
Binance nu publică istoric de lichidări, deci acestea nu apar (vezi heatmap-ul estimat din heatmap_oi.py).
"""
import time

import pandas as pd
import requests

from heatmap_oi import FAPI, INTERVALE, _descarca


def _funding(zile):
    start = int(time.time() * 1000) - zile * 86_400_000
    d = requests.get(FAPI + '/fapi/v1/fundingRate', params={'symbol': 'BTCUSDT', 'startTime': start, 'limit': 1000},
                     timeout=20).json()
    if not isinstance(d, list):
        raise ValueError(f"Binance fundingRate: {d}")
    return [{'t': int(x['fundingTime']), 'v': float(x['fundingRate']) * 100} for x in d]   # procente / 8h


def calculeaza(interval='1h'):
    ms, zile = INTERVALE[interval]
    p = {'symbol': 'BTCUSDT', 'period': interval}
    oi = _descarca('/futures/data/openInterestHist', p, ms, zile, 'timestamp')
    tk = _descarca('/futures/data/takerlongshortRatio', p, ms, zile, 'timestamp')
    ls = _descarca('/futures/data/globalLongShortAccountRatio', p, ms, zile, 'timestamp')
    kl = _descarca('/fapi/v1/klines', {'symbol': 'BTCUSDT', 'interval': interval}, ms, zile, 0)

    df = pd.DataFrame({'t': [int(x[0]) for x in kl], 'pret': [float(x[4]) for x in kl]}).drop_duplicates('t')
    df = df.merge(pd.DataFrame({'t': [int(x['timestamp']) for x in oi],
                                'oi': [float(x['sumOpenInterestValue']) for x in oi]}).drop_duplicates('t'), on='t', how='inner')
    df = df.merge(pd.DataFrame({'t': [int(x['timestamp']) for x in tk],
                                'delta_btc': [float(x['buyVol']) - float(x['sellVol']) for x in tk]}).drop_duplicates('t'),
                  on='t', how='left')
    df = df.merge(pd.DataFrame({'t': [int(x['timestamp']) for x in ls],
                                'ls': [float(x['longShortRatio']) for x in ls]}).drop_duplicates('t'), on='t', how='left')
    df = df.sort_values('t').reset_index(drop=True)
    df['cvd'] = (df['delta_btc'].fillna(0) * df['pret']).cumsum()

    funding = _funding(zile)
    pe_zi = 86_400_000 // ms
    oi_acum, oi_ieri = df['oi'].iloc[-1], df['oi'].iloc[max(0, len(df) - 1 - pe_zi)]
    return {
        'interval': interval,
        't': df['t'].tolist(), 'pret': df['pret'].tolist(), 'oi': df['oi'].tolist(),
        'cvd': df['cvd'].tolist(), 'ls': df['ls'].tolist(),
        'funding': funding,
        'rezumat': {
            'oi': oi_acum, 'oi_var_24h': (oi_acum / oi_ieri - 1) * 100 if oi_ieri else None,
            'funding': funding[-1]['v'] if funding else None,
            'funding_anual': funding[-1]['v'] * 3 * 365 if funding else None,
            'ls': df['ls'].dropna().iloc[-1] if df['ls'].notna().any() else None,
            'cvd_24h': df['cvd'].iloc[-1] - df['cvd'].iloc[max(0, len(df) - 1 - pe_zi)],
        },
    }
