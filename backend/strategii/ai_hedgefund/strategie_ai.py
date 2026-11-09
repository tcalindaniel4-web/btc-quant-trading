"""
STRATEGIA AI HEDGE FUND - "Ansamblu Trend & Momentum cu filtru de Funding" (long / cash, fără DCA)

Ideea: în loc să ghicim UN parametru (ex. SMA 200), întrebăm 12 "experți" independenți dacă
BTC e pe trend ascendent, pe orizonturi diferite (2 săptămâni -> 1 an). Procentul celor care
spun DA = scorul de trend (0..1) = cât din capital ținem în BTC.

  1. Trend (6 voturi):    Close > SMA(n),          n = 20, 40, 80, 120, 160, 200 zile
  2. Momentum (6 voturi): randament pe n zile > 0,  n = 14, 30, 60, 90, 180, 365 zile
  3. Filtru Funding:      dacă funding-ul mediu pe 7 zile > 0.05%/8h (piață supra-îndatorată pe long,
                          ~55%/an plătit de long-uri) -> expunerea se înjumătățește (risc de lichidări în cascadă)
  4. Execuție:            expunerea se rotunjește la trepte de 25% și se schimbă doar dacă ținta
                          s-a mutat cu > 15 puncte procentuale (evită tranzacții mărunte și comisioane)

Alese pe 2018-2022 (train) și validate pe 2023-2026 (test, date nefolosite la alegere).
Variante testate și RESPINSE (nu au rezistat pe date noi sau au stricat rezultatele):
Donchian 55/20, SMA200 simplu, EMA50/200, volatility targeting, crash-guard ATR, dip-buy RSI,
poziție "convexă" (100%/0% la consens) - bună pe train, mai slabă pe test => supra-ajustare.
"""
import numpy as np
import pandas as pd

CONFIG = {
    'sma_orizonturi': [20, 40, 80, 120, 160, 200],
    'mom_orizonturi': [14, 30, 60, 90, 180, 365],
    'funding_prag': 0.05,        # % / 8h, medie pe 7 zile
    'funding_reducere': 0.5,     # multiplicator expunere când funding-ul e supraîncălzit
    'pas': 0.25,                 # trepte de expunere: 0, 25, 50, 75, 100%
    'histerezis': 0.15,          # schimbăm ținta doar dacă diferența > 15pp
    'comision': 0.001,           # 0.10% Binance spot (taker)
    'slippage': 0.0005,          # 0.05% estimat
}


def calculeaza_indicatori(df, cfg=CONFIG):
    """Adaugă coloanele strategiei. Toți indicatorii folosesc DOAR trecutul (fără lookahead)."""
    df = df.copy()
    c = df['Close']
    for n in cfg['sma_orizonturi']:
        df[f'SMA_{n}'] = c.rolling(n).mean()
        df[f'V_trend_{n}'] = (c > df[f'SMA_{n}']).astype(float)
    for n in cfg['mom_orizonturi']:
        df[f'Mom_{n}'] = c / c.shift(n) - 1
        df[f'V_mom_{n}'] = (df[f'Mom_{n}'] > 0).astype(float)

    voturi_trend = [f'V_trend_{n}' for n in cfg['sma_orizonturi']]
    voturi_mom = [f'V_mom_{n}' for n in cfg['mom_orizonturi']]
    df['Scor_Trend'] = df[voturi_trend].mean(axis=1)
    df['Scor_Momentum'] = df[voturi_mom].mean(axis=1)
    df['Scor_Brut'] = (df['Scor_Trend'] + df['Scor_Momentum']) / 2

    df['Funding_7d'] = df['Funding_Rate'].rolling(7, min_periods=1).mean()
    df['Funding_Fierbinte'] = df['Funding_7d'] > cfg['funding_prag']
    df['Scor_Final'] = np.where(df['Funding_Fierbinte'], df['Scor_Brut'] * cfg['funding_reducere'], df['Scor_Brut'])

    # Context (afișat în log, NU intră în decizie - nu a îmbunătățit rezultatele pe date noi)
    r = c.pct_change()
    df['Volatilitate_30d'] = r.rolling(30).std() * np.sqrt(365)
    d = c.diff()
    castig = d.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    pierdere = (-d.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    df['RSI_14'] = 100 - 100 / (1 + castig / pierdere)
    df['Drawdown_ATH'] = c / c.cummax() - 1

    # Avem nevoie de 365 zile de istoric pentru toate voturile
    df['Valid'] = df[voturi_trend + voturi_mom].notna().all(axis=1) & c.shift(max(cfg['mom_orizonturi'])).notna()
    return df


def tinta_noua(scor, tinta_curenta, cfg=CONFIG):
    """Ținta de expunere (0..1) pentru mâine, dată fiind ținta actuală (histerezis)."""
    if scor is None or np.isnan(scor):
        return tinta_curenta
    t = round(scor / cfg['pas']) * cfg['pas']
    return t if abs(t - tinta_curenta) > cfg['histerezis'] else tinta_curenta


def explica(rand, cfg=CONFIG):
    """Text scurt: ce spune fiecare vot (pentru log-ul botului / licență)."""
    tr = ''.join('▲' if rand[f'V_trend_{n}'] else '▼' for n in cfg['sma_orizonturi'])
    mo = ''.join('▲' if rand[f'V_mom_{n}'] else '▼' for n in cfg['mom_orizonturi'])
    txt = (f"Trend SMA {cfg['sma_orizonturi']}: {tr} ({rand['Scor_Trend']:.0%}) | "
           f"Momentum {cfg['mom_orizonturi']}: {mo} ({rand['Scor_Momentum']:.0%})")
    if rand['Funding_Fierbinte']:
        txt += f" | ⚠️ Funding fierbinte {rand['Funding_7d']:.3f}% -> expunere x{cfg['funding_reducere']}"
    return txt
