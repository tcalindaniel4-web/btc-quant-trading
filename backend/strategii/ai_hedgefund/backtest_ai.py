"""
BACKTEST - Strategia AI Hedge Fund (Ansamblu Trend & Momentum + filtru Funding)

Realism:
  - semnalul se calculează la ÎNCHIDEREA zilei t și se execută la prețul de închidere t
    (= deschiderea t+1, BTC tranzacționează 24/7), deci fără informații din viitor;
  - comision 0.10% + slippage 0.05% la fiecare tranzacție;
  - fără levier, fără short: doar BTC sau USDT.

Rulare:
  python backend/strategii/ai_hedgefund/backtest_ai.py                       (2018 -> azi, $10.000)
  python backend/strategii/ai_hedgefund/backtest_ai.py --start 2023-01-01 --capital 1000
Salvează: ai_hedgefund/rezultate/tranzactii_backtest.csv, echitate_backtest.csv
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from date_ai import incarca_date
from strategie_ai import CONFIG, calculeaza_indicatori, tinta_noua

DIR = Path(__file__).resolve().parent
REZ_DIR = DIR / 'rezultate'


def ruleaza_backtest(df, start, end, capital, cfg=CONFIG, verbose=True):
    cost = cfg['comision'] + cfg['slippage']
    zile = df[(df['Data'] >= start) & (df['Data'] <= end) & df['Valid']]
    cash, btc, tinta = capital, 0.0, 0.0
    tranzactii, echitate = [], []

    for _, z in zile.iterrows():
        pret = z['Close']
        valoare = cash + btc * pret
        noua = tinta_noua(z['Scor_Final'], tinta, cfg)
        if noua != tinta:
            dorit_btc = valoare * noua / pret
            delta = dorit_btc - btc
            suma = abs(delta) * pret
            if delta > 0:   # CUMPĂRARE: plătim comisionul din cash
                btc_cumparat = (suma / (1 + cost)) / pret
                cash -= suma; btc += btc_cumparat
                actiune = 'BUY'
            else:           # VÂNZARE
                cash += suma * (1 - cost); btc -= abs(delta)
                actiune = 'SELL'
            tranzactii.append({'Data': z['Data'], 'Actiune': actiune, 'Pret': round(pret, 2),
                               'Suma_USD': round(suma, 2), 'Expunere_veche': tinta, 'Expunere_noua': noua,
                               'Scor': round(z['Scor_Final'], 3), 'Funding_fierbinte': bool(z['Funding_Fierbinte']),
                               'Valoare_portofoliu': round(cash + btc * pret, 2)})
            tinta = noua
        echitate.append({'Data': z['Data'], 'Pret': pret, 'Expunere': tinta, 'Valoare': cash + btc * pret})

    eq = pd.DataFrame(echitate)
    eq['BuyHold'] = capital * eq['Pret'] / eq['Pret'].iloc[0]
    return pd.DataFrame(tranzactii), eq


def statistici(serie):
    ret = serie.pct_change().dropna()
    ani = len(serie) / 365
    cagr = (serie.iloc[-1] / serie.iloc[0]) ** (1 / ani) - 1
    dd = (serie / serie.cummax() - 1).min()
    sharpe = ret.mean() / ret.std() * np.sqrt(365) if ret.std() > 0 else 0.0
    return {'Final': serie.iloc[-1], 'Total': serie.iloc[-1] / serie.iloc[0] - 1, 'CAGR': cagr,
            'MaxDD': dd, 'Sharpe': sharpe, 'Calmar': cagr / abs(dd) if dd < 0 else 0.0}


def raport(tr, eq, capital):
    s_ai, s_bh = statistici(eq['Valoare']), statistici(eq['BuyHold'])
    print("=" * 78)
    print(f" 🤖 AI HEDGE FUND - BACKTEST  {eq['Data'].iloc[0]} -> {eq['Data'].iloc[-1]}  (capital ${capital:,.0f})")
    print("=" * 78)
    print(f"{'':22}{'STRATEGIA AI':>18}{'BUY & HOLD':>18}")
    print(f"{'Valoare finală':22}{s_ai['Final']:>17,.0f}${s_bh['Final']:>17,.0f}$")
    print(f"{'Randament total':22}{s_ai['Total']:>18.1%}{s_bh['Total']:>18.1%}")
    print(f"{'Randament anual (CAGR)':22}{s_ai['CAGR']:>18.1%}{s_bh['CAGR']:>18.1%}")
    print(f"{'Drawdown maxim':22}{s_ai['MaxDD']:>18.1%}{s_bh['MaxDD']:>18.1%}")
    print(f"{'Sharpe':22}{s_ai['Sharpe']:>18.2f}{s_bh['Sharpe']:>18.2f}")
    print(f"{'Calmar (CAGR/DD)':22}{s_ai['Calmar']:>18.2f}{s_bh['Calmar']:>18.2f}")
    print(f"{'Expunere medie BTC':22}{eq['Expunere'].mean():>18.0%}{1:>18.0%}")
    print(f"{'Tranzacții':22}{len(tr):>18}{1:>18}")
    if len(tr):
        print(f"{'Comisioane plătite ~':22}{(tr['Suma_USD'] * (CONFIG['comision'] + CONFIG['slippage'])).sum():>17,.0f}$")

    print("\n📅 Pe ani:")
    eq['An'] = eq['Data'].str[:4]
    for an, g in eq.groupby('An'):
        a = g['Valoare'].iloc[-1] / g['Valoare'].iloc[0] - 1
        b = g['BuyHold'].iloc[-1] / g['BuyHold'].iloc[0] - 1
        dd = (g['Valoare'] / g['Valoare'].cummax() - 1).min()
        print(f"   {an}:  AI {a:>+8.1%} (DD {dd:>6.1%})  |  B&H {b:>+8.1%}  |  expunere medie {g['Expunere'].mean():.0%}")

    print("\n🧾 Ultimele 10 tranzacții:")
    for _, t in tr.tail(10).iterrows():
        sem = '🟢' if t['Actiune'] == 'BUY' else '🔴'
        f = ' (funding fierbinte)' if t['Funding_fierbinte'] else ''
        print(f"   {sem} {t['Data']} {t['Actiune']:4} ${t['Suma_USD']:>10,.0f} @ {t['Pret']:>9,.0f}$ | "
              f"expunere {t['Expunere_veche']:.0%} -> {t['Expunere_noua']:.0%}{f}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument('--start', default='2018-01-01')
    p.add_argument('--end', default='2100-01-01')
    p.add_argument('--capital', type=float, default=10000.0)
    a = p.parse_args()

    df = incarca_date()
    df = df[df['Inchisa']].reset_index(drop=True)  # doar zile închise
    df = calculeaza_indicatori(df)
    tr, eq = ruleaza_backtest(df, a.start, a.end, a.capital)
    raport(tr, eq, a.capital)

    REZ_DIR.mkdir(exist_ok=True)
    tr.to_csv(REZ_DIR / 'tranzactii_backtest.csv', index=False)
    eq.to_csv(REZ_DIR / 'echitate_backtest.csv', index=False)
    print(f"\n💾 Salvat: {REZ_DIR / 'tranzactii_backtest.csv'} și echitate_backtest.csv")
