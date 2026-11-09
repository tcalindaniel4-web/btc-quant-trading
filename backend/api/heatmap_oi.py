"""
HEATMAP ESTIMAT AL LICHIDĂRILOR, construit din Open Interest-ul Binance Futures (BTCUSDT perpetual).

Date (API public Binance, fără cheie, ~30 de zile de istoric):
  - Open Interest istoric (valoare în USD) pe intervale de 15m / 1h / 4h
  - raportul taker buy/sell pe aceleași intervale
  - lumânări futures (open / high / low / close)

Modelul (aceeași idee ca la heatmap-urile comerciale de lichidare, dar calculat transparent):
  1. Dacă OI crește într-un interval, ΔOI = poziții NOI deschise la prețul tipic al intervalului.
  2. Pozițiile noi se împart în LONG / SHORT după cota de cumpărări agresive (taker buy / total).
  3. Fiecare poziție are un levier presupus (distribuția LEVIERE). Prețul de lichidare aproximat:
        long:  intrare × (1 − 1/levier + marjă_mentenanță)
        short: intrare × (1 + 1/levier − marjă_mentenanță)
  4. Când prețul atinge un nivel (low ≤ nivel long / high ≥ nivel short), pozițiile de acolo se
     consideră lichidate și dispar din hartă.
  5. Dacă OI scade, o parte din poziții s-au închis: toate nivelurile se reduc proporțional.
Rezultat: pentru fiecare moment, câți USD (estimat) s-ar lichida la fiecare nivel de preț.
E un MODEL: levierul real al fiecărui trader nu e public, iar datele sunt doar de pe Binance.
"""
import time

import numpy as np
import pandas as pd
import requests

FAPI = 'https://fapi.binance.com'
LEVIERE = {10: 0.30, 25: 0.30, 50: 0.25, 100: 0.15}   # distribuție presupusă a levierului
MARJA_MENTENANTA = 0.004                              # ~0.4% (treapta de bază Binance BTCUSDT)
NR_NIVELURI = 140

INTERVALE = {   # interval -> (milisecunde, zile de istoric)
    '15m': (15 * 60_000, 5),
    '1h': (60 * 60_000, 29),
    '4h': (4 * 60 * 60_000, 29),
}


def _descarca(cale, params, interval_ms, zile, cheie_timp):
    """Descarcă paginat, în ferestre explicite [start, end] de max 500 de intervale (endpoint-urile
    /futures/data ignoră startTime fără endTime și întorc doar ultimele 500 de rânduri)."""
    acum = int(time.time() * 1000)
    start = acum - zile * 86_400_000
    rezultate = []
    while start < acum:
        end = min(start + 499 * interval_ms, acum)
        r = requests.get(FAPI + cale, params={**params, 'limit': 500, 'startTime': start, 'endTime': end}, timeout=20)
        d = r.json()
        if not isinstance(d, list):
            raise ValueError(f"Binance {cale}: {d}")
        rezultate.extend(d)
        start = end + 1
    return rezultate


def descarca_date(interval='1h'):
    ms, zile = INTERVALE[interval]
    oi = _descarca('/futures/data/openInterestHist', {'symbol': 'BTCUSDT', 'period': interval}, ms, zile, 'timestamp')
    taker = _descarca('/futures/data/takerlongshortRatio', {'symbol': 'BTCUSDT', 'period': interval}, ms, zile, 'timestamp')
    kl = _descarca('/fapi/v1/klines', {'symbol': 'BTCUSDT', 'interval': interval}, ms, zile, 0)

    df_oi = pd.DataFrame({'t': [int(x['timestamp']) for x in oi], 'oi': [float(x['sumOpenInterestValue']) for x in oi]})
    df_tk = pd.DataFrame({'t': [int(x['timestamp']) for x in taker],
                          'cota_buy': [float(x['buyVol']) / max(float(x['buyVol']) + float(x['sellVol']), 1e-9) for x in taker]})
    df_k = pd.DataFrame({'t': [int(x[0]) for x in kl], 'open': [float(x[1]) for x in kl], 'high': [float(x[2]) for x in kl],
                         'low': [float(x[3]) for x in kl], 'close': [float(x[4]) for x in kl]})
    df = (df_k.drop_duplicates('t').merge(df_oi.drop_duplicates('t'), on='t', how='inner')
          .merge(df_tk.drop_duplicates('t'), on='t', how='left').sort_values('t').reset_index(drop=True))
    df['cota_buy'] = df['cota_buy'].fillna(0.5)
    # OI de la începutul intervalului următor - OI de la începutul acestuia = poziții deschise / închise ÎN interval
    df['delta_oi'] = df['oi'].shift(-1) - df['oi']
    return df


def construieste_heatmap(df, nr_niveluri=NR_NIVELURI):
    jos, sus = df['low'].min() * 0.90, df['high'].max() * 1.10
    pas = (sus - jos) / nr_niveluri
    centre = jos + pas * (np.arange(nr_niveluri) + 0.5)

    long_act = np.zeros(nr_niveluri)    # USD estimat care s-ar lichida la fiecare nivel (pozițiile long)
    short_act = np.zeros(nr_niveluri)
    mat_long, mat_short = [], []

    def idx(pret):
        return int(np.clip((pret - jos) // pas, 0, nr_niveluri - 1))

    for r in df.itertuples():
        # 1. lichidări: prețul a trecut prin niveluri în acest interval
        long_act[centre >= r.low] = 0.0
        short_act[centre <= r.high] = 0.0
        # 2. poziții închise (OI scade) -> reducere proporțională
        if not np.isnan(r.delta_oi) and r.delta_oi < 0 and r.oi > 0:
            f = max(0.0, 1 + r.delta_oi / r.oi)
            long_act *= f
            short_act *= f
        mat_long.append(long_act.copy())
        mat_short.append(short_act.copy())
        # 3. poziții noi (OI crește) -> niveluri de lichidare noi (active din intervalul următor)
        if not np.isnan(r.delta_oi) and r.delta_oi > 0:
            intrare = (r.high + r.low + r.close) / 3
            nou_long, nou_short = r.delta_oi * r.cota_buy, r.delta_oi * (1 - r.cota_buy)
            for lev, w in LEVIERE.items():
                long_act[idx(intrare * (1 - 1 / lev + MARJA_MENTENANTA))] += nou_long * w
                short_act[idx(intrare * (1 + 1 / lev - MARJA_MENTENANTA))] += nou_short * w

    return centre, pas, np.array(mat_long), np.array(mat_short), long_act, short_act


def clustere(centre, long_act, short_act, pret, n=6):
    """Cele mai mari zone de lichidare sub preț (long) și peste preț (short), din starea curentă."""
    def top(valori, masca, tip):
        ids = [i for i in np.argsort(valori)[::-1] if masca[i] and valori[i] > 0][:n]
        return [{'tip': tip, 'pret': float(centre[i]), 'usd': float(valori[i]),
                 'distanta_pct': float((centre[i] / pret - 1) * 100)} for i in sorted(ids, key=lambda i: abs(centre[i] - pret))]
    return {'sub_pret': top(long_act, centre < pret, 'LONG'), 'peste_pret': top(short_act, centre > pret, 'SHORT')}


def calculeaza(interval='1h'):
    if interval not in INTERVALE:
        raise ValueError(f"Interval invalid. Alege: {', '.join(INTERVALE)}")
    df = descarca_date(interval)
    centre, pas, m_long, m_short, long_act, short_act = construieste_heatmap(df)
    pret = float(df['close'].iloc[-1])
    in_banda = lambda v, m: float(v[m].sum())
    banda5 = (centre > pret * 0.95) & (centre < pret * 1.05)
    return {
        'interval': interval, 'zile': INTERVALE[interval][1],
        'timp': [pd.to_datetime(t, unit='ms', utc=True).strftime('%Y-%m-%d %H:%M') for t in df['t']],
        'niveluri': [round(float(c), 1) for c in centre], 'pas_nivel': float(pas),
        # matrice timp × nivel, în mii USD (rotunjit) - pentru desenarea heatmap-ului
        'long_k': np.round(m_long / 1000).astype(int).tolist(),
        'short_k': np.round(m_short / 1000).astype(int).tolist(),
        'pret': {k: df[k].round(1).tolist() for k in ('open', 'high', 'low', 'close')},
        'oi': (df['oi'] / 1e9).round(4).tolist(), 'cota_buy': df['cota_buy'].round(4).tolist(),
        'pret_curent': pret, 'oi_curent': float(df['oi'].iloc[-1]),
        'oi_variatie_pct': float((df['oi'].iloc[-1] / df['oi'].iloc[0] - 1) * 100),
        'clustere': clustere(centre, long_act, short_act, pret),
        'sumar': {'long_sub_5pct': in_banda(long_act, banda5 & (centre < pret)),
                  'short_peste_5pct': in_banda(short_act, banda5 & (centre > pret)),
                  'long_total': float(long_act.sum()), 'short_total': float(short_act.sum())},
        'model': {'leviere': {str(k): v for k, v in LEVIERE.items()}, 'marja_mentenanta': MARJA_MENTENANTA,
                  'sursa': 'Binance Futures BTCUSDT (Open Interest, taker buy/sell, lumânări)'},
    }


if __name__ == '__main__':
    t = time.time()
    d = calculeaza('1h')
    print(f"{len(d['timp'])} intervale × {len(d['niveluri'])} niveluri în {time.time() - t:.1f}s | preț {d['pret_curent']:,.0f}")
    print(f"long ≤5% sub preț: ${d['sumar']['long_sub_5pct'] / 1e6:,.0f}M | short ≤5% peste: ${d['sumar']['short_peste_5pct'] / 1e6:,.0f}M")
    for c in d['clustere']['peste_pret'] + d['clustere']['sub_pret']:
        print(f"  {c['tip']:5} ${c['pret']:>9,.0f} ({c['distanta_pct']:+.1f}%)  ~${c['usd'] / 1e6:,.1f}M")
