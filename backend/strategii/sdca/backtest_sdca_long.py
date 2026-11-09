"""
BACKTEST - Strategia SDCA (Smart DCA pe Master_Index)

Folosește EXACT aceeași funcție de decizie ca botul live (strategie_sdca.decide), zi cu zi.
Comision 0.10% + slippage 0.05% pe fiecare tranzacție.

Afișează fiecare tranzacție: DE CE s-a făcut, cu câți bani, cât BTC, cash / BTC / valoarea
portofoliului după, profitul realizat la vânzări și P/L-ul total până în acel moment.
Tranzacțiile se salvează și în backend/strategii/sdca/rezultate/tranzactii_sdca.csv.

Rulare (din folderul proiectului):
  python backend/strategii/sdca/backtest_sdca_long.py                       raport complet SDCA v2, 2023-02 -> azi
  python backend/strategii/sdca/backtest_sdca_long.py --start 2025-01-01 --capital 5000
  python backend/strategii/sdca/backtest_sdca_long.py --v1                  aceleași detalii pentru regulile vechi
  python backend/strategii/sdca/backtest_sdca_long.py --robustete           pornire din fiecare lună (2023-03 .. 2025-06)
"""
import argparse
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

SDCA_DIR = Path(__file__).resolve().parent
REZ_DIR = SDCA_DIR / 'rezultate'
sys.path.insert(0, str(SDCA_DIR.parent.parent / 'pipeline'))
from data_loader import incarca_dataset  # noqa: E402
from strategie_sdca import PRAG_MVRV_TOP, adauga_indicatori, decide, stare_noua, zile_intre  # noqa: E402

warnings.filterwarnings('ignore')

# Prima zi cu toate datele on-chain (MVRV/SOPR gratuit din 2022-11 + 90 zile pentru Z_SOPR + 7 zile întârziere)
START_IMPLICIT = '2023-02-15'
COST = 0.0015  # 0.10% comision + 0.05% slippage

TIPURI = ['FRONT-LOAD MASIV', 'AGRESIV DCA', 'MICRO DCA', 'S/R BOUNCE', 'MACRO TOP 70%',
          'MOONBAG FOMO', 'MOONBAG PANIC', 'DIAMOND HANDS ACTIVAT', 'DIAMOND HANDS DEZACTIVAT',
          'FALS TOP', 'BEAR MARKET RESET']


def motiv(mesaj):
    for t in TIPURI:
        if t in mesaj:
            return t
    return mesaj.split('|')[0].strip()


def _de_ce_acum(st_inainte, z, zile_min, scadere):
    """Care condiție de timp / preț a permis cumpărarea (pentru DCA)."""
    zile = st_inainte['zile_de_la_buy'] + zile_intre(st_inainte['ultima_rulare'], z['Data']) \
        if st_inainte['ultima_rulare'] not in (None, 'N/A') else 999
    if st_inainte['ultimul_pret_buy'] == 0 or zile >= 900:
        return "prima cumpărare"
    if zile >= zile_min:
        return f"au trecut {zile} zile de la ultima cumpărare (minim {zile_min})"
    var = z['Close'] / st_inainte['ultimul_pret_buy'] - 1
    return f"prețul a scăzut cu {abs(var):.1%} față de ultima cumpărare (${st_inainte['ultimul_pret_buy']:,.0f}; prag -{scadere:.0%})"


def explicatie(tip, z, zi, st_inainte):
    """Explicația în cuvinte a deciziei, cu valorile indicatorilor din ziua respectivă."""
    Z = f"Master_Index {z['Master_Index']:+.2f}"
    if tip == 'MACRO TOP 70%':
        dd = (z['Cycle_Peak_90d'] - z['Close']) / z['Cycle_Peak_90d']
        declansator = (f"prețul e cu {dd:.1%} sub vârful pe 90 de zile (${z['Cycle_Peak_90d']:,.0f})" if dd >= 0.10
                       else f"prețul a coborât sub media pe 50 de zile (${z['SMA_50']:,.0f})")
        return (f"alerta de euforie era deja armată (Master_Index ≥ 1.5 cu MVRV ajustat ≥ {PRAG_MVRV_TOP:.2f}), "
                f"iar acum trendul s-a epuizat: {declansator} → vindem 70% (MVRV azi {z['Adjusted_MVRV']:.2f})")
    return {
        'FRONT-LOAD MASIV': f"{Z} < -0.5 (piață subevaluată) și e prima intrare a ciclului → investim 70% din cash",
        'AGRESIV DCA': f"{Z} < -0.5 (subevaluat) și {_de_ce_acum(st_inainte, z, 7, 0.10)} → 40% din cash",
        'MICRO DCA': f"{Z} între -0.5 și 0 (ușor subevaluat) și {_de_ce_acum(st_inainte, z, 14, 0.05)} → 10% din cash",
        'S/R BOUNCE': f"{Z} neutru (0..1) și prețul e la ±5% de suportul ${st_inainte['nivel_suport_curent']:,.0f} → 20% din cash",
        'MOONBAG FOMO': f"prețul a urcat ≥20% peste vânzarea de 70% (${st_inainte['pret_vanzare_70']:,.0f}) → vindem restul",
        'MOONBAG PANIC': f"prețul a scăzut ≥22% sub vânzarea de 70% (${st_inainte['pret_vanzare_70']:,.0f}) → salvăm restul",
        'DIAMOND HANDS ACTIVAT': "prețul e cu ≥30% peste prețul mediu de cumpărare → nu mai cumpărăm, ținem poziția",
        'DIAMOND HANDS DEZACTIVAT': f"{Z} < -1 (capitulare) → se pot relua cumpărările",
        'FALS TOP': f"prețul a depășit vârful la care am vândut (${st_inainte['macro_top_trecut']:,.0f}) → nu era top de ciclu, reluăm acumularea",
        'BEAR MARKET RESET': f"prețul a scăzut 40% de la vârful ciclului (${st_inainte['ultimul_peak_cunoscut']:,.0f}) → începe un ciclu nou de acumulare",
    }.get(tip, '')


def simuleaza(df, start, end, capital=10000.0, v2=True):
    zile = df[(df['Data'] >= start) & (df['Data'] <= end)]
    st = stare_noua(capital)
    tranzactii, evenimente, valori, comisioane = [], [], [], 0.0
    for _, z in zile.iterrows():
        inainte = dict(st)
        pret_mediu = inainte['total_investit'] / inainte['btc'] if inainte['btc'] > 0 else 0.0
        mesaje = decide(st, z, v2=v2)
        delta_btc = st['btc'] - inainte['btc']
        suma = abs(delta_btc) * z['Close']
        comision = suma * COST
        if suma > 0:
            st['cash'] -= comision
            comisioane += comision

        for m in mesaje:
            tip = motiv(m)
            if tip in ('DIAMOND HANDS ACTIVAT', 'DIAMOND HANDS DEZACTIVAT', 'FALS TOP', 'BEAR MARKET RESET'):
                evenimente.append({'Data': z['Data'], 'Eveniment': tip, 'De_ce': explicatie(tip, z, z['Data'], inainte)})

        if suma > 0:
            tip = next(motiv(m) for m in mesaje if 'BUY' in m or 'SELL' in m)
            vanzare = delta_btc < 0
            profit = (z['Close'] - pret_mediu) * abs(delta_btc) - comision if vanzare else None
            valoare = st['cash'] + st['btc'] * z['Close']
            tranzactii.append({
                'Data': z['Data'], 'Tip': 'SELL' if vanzare else 'BUY', 'Motiv': tip,
                'Pret': z['Close'], 'Suma_USD': suma, 'BTC': abs(delta_btc), 'Comision': comision,
                'Pret_mediu': pret_mediu if vanzare else (st['total_investit'] / st['btc'] if st['btc'] > 0 else 0),
                'Profit_realizat': profit, 'Cash_dupa': st['cash'], 'BTC_dupa': st['btc'],
                'Valoare_portofoliu': valoare, 'PL_total_%': (valoare / capital - 1) * 100,
                'Master_Index': z['Master_Index'], 'MVRV_ajustat': z['Adjusted_MVRV'],
                'De_ce': explicatie(tip, z, z['Data'], inainte)})
        valori.append(st['cash'] + st['btc'] * z['Close'])
    return pd.Series(valori, index=zile['Data'].values), pd.DataFrame(tranzactii), pd.DataFrame(evenimente), comisioane, st


def statistici(eq):
    r = eq.pct_change().dropna()
    ani = max(len(eq) / 365, 1 / 365)
    cagr = (eq.iloc[-1] / eq.iloc[0]) ** (1 / ani) - 1
    dd = (eq / eq.cummax() - 1).min()
    sharpe = r.mean() / r.std() * np.sqrt(365) if r.std() > 0 else 0.0
    return {'Final': eq.iloc[-1], 'Total': eq.iloc[-1] / eq.iloc[0] - 1, 'CAGR': cagr, 'MaxDD': dd, 'Sharpe': sharpe}


def buy_hold(df, start, end, capital=10000.0):
    z = df[(df['Data'] >= start) & (df['Data'] <= end)]
    return pd.Series(capital * z['Close'].values / z['Close'].iloc[0], index=z['Data'].values)


def afiseaza_jurnal(tr, ev):
    print("\n🧾 JURNAL COMPLET (fiecare tranzacție și de ce a fost făcută)")
    print("-" * 110)
    linii = [('T', r) for _, r in tr.iterrows()] + [('E', r) for _, r in ev.iterrows()]
    linii.sort(key=lambda x: (x[1]['Data'], 0 if x[0] == 'E' else 1))
    nr = 0
    for fel, r in linii:
        if fel == 'E':
            print(f"\n   ⚑ {r['Data']}  {r['Eveniment']}")
            print(f"      ↳ {r['De_ce']}")
            continue
        nr += 1
        semn = '🟢' if r['Tip'] == 'BUY' else '🔴'
        print(f"\n#{nr:<3} {semn} {r['Data']}  {r['Tip']:4} {r['Motiv']:<17} | {r['BTC']:.6f} BTC × ${r['Pret']:,.2f} = ${r['Suma_USD']:,.2f}"
              f"  (comision ${r['Comision']:,.2f})")
        print(f"      ↳ De ce: {r['De_ce']}")
        if r['Tip'] == 'SELL':
            pct = (r['Pret'] / r['Pret_mediu'] - 1) * 100 if r['Pret_mediu'] > 0 else 0
            print(f"      💰 Profit realizat: ${r['Profit_realizat']:+,.2f}  (vândut la ${r['Pret']:,.0f}, preț mediu ${r['Pret_mediu']:,.0f}, {pct:+.1f}%)")
        else:
            print(f"      📐 Preț mediu de cumpărare acum: ${r['Pret_mediu']:,.2f}")
        print(f"      💼 După: cash ${r['Cash_dupa']:,.2f} | BTC {r['BTC_dupa']:.6f} | portofoliu ${r['Valoare_portofoliu']:,.2f}"
              f" | P/L total {r['PL_total_%']:+.2f}%")


def raport(df, start, end, capital, v2=True):
    eq, tr, ev, comisioane, st = simuleaza(df, start, end, capital, v2=v2)
    bh = buy_hold(df, start, end, capital)
    s, sb = statistici(eq), statistici(bh)
    nume = 'SDCA v2' if v2 else 'SDCA v1 (vechi)'
    pret_final = df[df['Data'] <= end]['Close'].iloc[-1]

    print("=" * 110)
    print(f" 📊 {nume} - BACKTEST  {eq.index[0]} -> {eq.index[-1]}")
    print("=" * 110)

    afiseaza_jurnal(tr, ev)

    cumparari = tr[tr['Tip'] == 'BUY'] if len(tr) else tr
    vanzari = tr[tr['Tip'] == 'SELL'] if len(tr) else tr
    profit_realizat = vanzari['Profit_realizat'].sum() if len(vanzari) else 0.0
    valoare_btc = st['btc'] * pret_final
    pret_mediu = st['total_investit'] / st['btc'] if st['btc'] > 0 else 0.0
    profit_nerealizat = valoare_btc - st['total_investit'] if st['btc'] > 0 else 0.0

    print("\n" + "=" * 110)
    print(f" 📋 RAPORT FINAL - {nume}")
    print("=" * 110)
    print(f"Capital inițial:          ${capital:,.2f}")
    print(f"Capital final:            ${s['Final']:,.2f}")
    print(f"Profit net:               ${s['Final'] - capital:+,.2f}")
    print(f"Randament (ROI):          {s['Total']:+.2%}   (anual {s['CAGR']:+.1%})")
    print(f"Drawdown maxim:           {s['MaxDD']:.1%}")
    print("-" * 60)
    print(f"Cash rămas:               ${st['cash']:,.2f}")
    print(f"BTC deținut:              {st['btc']:.6f} BTC = ${valoare_btc:,.2f} (la ${pret_final:,.2f})")
    if st['btc'] > 0:
        print(f"Preț mediu poziție:       ${pret_mediu:,.2f}  → profit nerealizat ${profit_nerealizat:+,.2f}")
    print(f"Profit realizat (vânzări): ${profit_realizat:+,.2f}")
    print("-" * 60)
    print(f"Tranzacții totale:        {len(tr)}  ({len(cumparari)} cumpărări, {len(vanzari)} vânzări)")
    if len(tr):
        print(f"Total cumpărat:           ${cumparari['Suma_USD'].sum():,.2f}")
        print(f"Total vândut:             ${vanzari['Suma_USD'].sum():,.2f}")
        print(f"Comisioane + slippage:    ${comisioane:,.2f}")
        print("Pe tipuri:                " + ", ".join(f"{k} ×{v}" for k, v in tr['Motiv'].value_counts().items()))

    print(f"\n⚖️ Reper: dacă ai fi cumpărat BTC cu tot capitalul în prima zi și l-ai fi ținut (Buy & Hold):")
    print(f"{'':22}{nume:>18}{'BUY & HOLD':>15}")
    print(f"{'Capital final':22}{s['Final']:>17,.0f}${sb['Final']:>14,.0f}$")
    print(f"{'Randament total':22}{s['Total']:>18.1%}{sb['Total']:>15.1%}")
    print(f"{'Drawdown maxim':22}{s['MaxDD']:>18.1%}{sb['MaxDD']:>15.1%}")
    print(f"{'Sharpe':22}{s['Sharpe']:>18.2f}{sb['Sharpe']:>15.2f}")

    REZ_DIR.mkdir(exist_ok=True)
    fisier = REZ_DIR / f"tranzactii_sdca_{'v2' if v2 else 'v1'}.csv"
    if len(tr):
        tr.round(6).to_csv(fisier, index=False)
        print(f"\n💾 Toate tranzacțiile au fost salvate în: {fisier}")


def robustete(df, end, capital):
    starturi = pd.date_range('2023-03-01', '2025-06-01', freq='MS').strftime('%Y-%m-%d').tolist()
    rez = {'SDCA v2': [], 'SDCA v1': [], 'Buy&Hold': []}
    dd = {'SDCA v2': [], 'SDCA v1': [], 'Buy&Hold': []}
    for s in starturi:
        for nume, serie in (('SDCA v2', simuleaza(df, s, end, capital, True)[0]),
                            ('SDCA v1', simuleaza(df, s, end, capital, False)[0]),
                            ('Buy&Hold', buy_hold(df, s, end, capital))):
            rez[nume].append(serie.iloc[-1] / capital - 1)
            dd[nume].append((serie / serie.cummax() - 1).min())
    print("=" * 80)
    print(f" 🔁 ROBUSTEȚE: {len(starturi)} porniri lunare ({starturi[0]} .. {starturi[-1]}) -> azi")
    print("=" * 80)
    print(f"{'':12}{'medie':>10}{'mediană':>10}{'cel mai slab':>14}{'cel mai bun':>13}{'DD mediu':>11}{'DD maxim':>11}")
    for nume in rez:
        r, d = np.array(rez[nume]), np.array(dd[nume])
        print(f"{nume:12}{r.mean():>+10.1%}{np.median(r):>+10.1%}{r.min():>+14.1%}{r.max():>+13.1%}{d.mean():>11.1%}{d.min():>11.1%}")
    bate = sum(a > b for a, b in zip(rez['SDCA v2'], rez['SDCA v1']))
    print(f"\nSDCA v2 bate v1 în {bate}/{len(starturi)} porniri.")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument('--start', default=START_IMPLICIT)
    p.add_argument('--end', default='2100-01-01')
    p.add_argument('--capital', type=float, default=10000.0)
    p.add_argument('--v1', action='store_true', help='jurnalul detaliat pentru regulile vechi')
    p.add_argument('--robustete', action='store_true')
    a = p.parse_args()

    df = incarca_dataset()
    if df is None or df.empty:
        sys.exit(1)
    df = adauga_indicatori(df)
    if a.robustete:
        robustete(df, a.end, a.capital)
    else:
        if a.start < START_IMPLICIT:
            print(f"[i] Datele on-chain complete încep pe {START_IMPLICIT}; backtest-ul pornește de acolo.")
        raport(df, max(a.start, START_IMPLICIT), a.end, a.capital, v2=not a.v1)
