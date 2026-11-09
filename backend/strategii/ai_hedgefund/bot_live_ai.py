"""
🤖 AI HEDGE FUND - SIMULATOR LIVE (paper trading, NU trimite ordine reale)

Ce face, la fiecare ciclu (implicit 15 minute):
  1. Ia prețul BTC LIVE de pe Binance și evaluează portofoliul virtual (mark-to-market).
  2. Când se închide o zi nouă (00:00 UTC = 02:00/03:00 ora României), descarcă lumânarea,
     recalculează cei 12 "experți" și, dacă ținta de expunere se schimbă, EXECUTĂ VIRTUAL
     tranzacția la prețul live (cu comision + slippage), exact ca în backtest.
  3. Între închideri afișează și "semnalul provizoriu": ce ar face dacă ziua s-ar închide acum
     (doar informativ - decizia se ia pe zile închise, ca în backtest, ca să nu se contrazică).

Fișiere: ai_hedgefund/stare_live.json (portofoliul), ai_hedgefund/rezultate/jurnal_live.csv (tranzacții)

Rulare:
  python backend/strategii/ai_hedgefund/bot_live_ai.py                      simulator continuu (Ctrl+C oprește)
  python backend/strategii/ai_hedgefund/bot_live_ai.py --o-data             un singur ciclu
  python backend/strategii/ai_hedgefund/bot_live_ai.py --capital 50000      capital la PRIMA pornire (implicit 10000)
  python backend/strategii/ai_hedgefund/bot_live_ai.py --interval 5         ciclu la 5 minute
  python backend/strategii/ai_hedgefund/bot_live_ai.py --offline            fără internet: doar datele salvate
  python backend/strategii/ai_hedgefund/bot_live_ai.py --reset              șterge portofoliul virtual și începe de la zero
"""
import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from date_ai import DATA_DIR, actualizeaza_tot, incarca_date, pret_curent
from strategie_ai import CONFIG, calculeaza_indicatori, explica, tinta_noua

DIR = Path(__file__).resolve().parent
STARE = DIR / 'stare_live.json'
JURNAL = DIR / 'rezultate' / 'jurnal_live.csv'


# ----------------------------------------------------------------------------- stare
def incarca_stare():
    if STARE.exists():
        return json.loads(STARE.read_text(encoding='utf-8'))
    return None


def salveaza_stare(s):
    STARE.write_text(json.dumps(s, indent=4, ensure_ascii=False), encoding='utf-8')


def stare_noua(capital, pret):
    return {'capital_initial': capital, 'cash': capital, 'btc': 0.0, 'tinta': 0.0,
            'ultima_zi_procesata': None, 'pornit_la': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'pret_la_pornire': pret, 'nr_tranzactii': 0, 'comisioane': 0.0}


def scrie_jurnal(rand):
    JURNAL.parent.mkdir(exist_ok=True)
    pd.DataFrame([rand]).to_csv(JURNAL, mode='a', header=not JURNAL.exists(), index=False)


# ----------------------------------------------------------------------------- date
def ultima_zi_inchisa_utc():
    return (pd.Timestamp.now(tz=timezone.utc).normalize() - pd.Timedelta(days=1)).strftime('%Y-%m-%d')


def date_la_zi():
    """True dacă fișierul local are deja ultima zi închisă (UTC)."""
    p = DATA_DIR / 'btc_1d.csv'
    if not p.exists():
        return False
    k = pd.read_csv(p, usecols=['Data', 'Inchisa'])
    inchise = k[k['Inchisa']]
    return len(inchise) > 0 and inchise['Data'].iloc[-1] >= ultima_zi_inchisa_utc()


# ----------------------------------------------------------------------------- execuție
def executa(stare, noua, pret, zi_semnal, rand):
    cost = CONFIG['comision'] + CONFIG['slippage']
    valoare = stare['cash'] + stare['btc'] * pret
    delta = valoare * noua / pret - stare['btc']
    suma = abs(delta) * pret
    if delta > 0:
        stare['btc'] += (suma / (1 + cost)) / pret
        stare['cash'] -= suma
        actiune = 'BUY'
    else:
        stare['cash'] += suma * (1 - cost)
        stare['btc'] -= abs(delta)
        actiune = 'SELL'
    veche = stare['tinta']
    stare['tinta'] = noua
    stare['nr_tranzactii'] += 1
    stare['comisioane'] += suma * cost / (1 + cost) if delta > 0 else suma * cost

    sem = '🟢' if actiune == 'BUY' else '🔴'
    print(f"\n   {sem} TRANZACȚIE: {actiune} ${suma:,.2f} BTC @ ${pret:,.2f}  |  expunere {veche:.0%} -> {noua:.0%}")
    scrie_jurnal({'Executat_la': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'Zi_semnal': zi_semnal,
                  'Actiune': actiune, 'Pret': round(pret, 2), 'Suma_USD': round(suma, 2),
                  'Expunere_veche': veche, 'Expunere_noua': noua, 'Scor': round(rand['Scor_Final'], 3),
                  'Funding_fierbinte': bool(rand['Funding_Fierbinte']),
                  'Valoare_portofoliu': round(stare['cash'] + stare['btc'] * pret, 2)})


# ----------------------------------------------------------------------------- ciclu
def ciclu(capital_start, offline):
    acum = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print("\n" + "=" * 86)
    print(f" 🤖 AI HEDGE FUND - SIMULATOR LIVE  ({acum})" + ("  [OFFLINE]" if offline else ""))
    print("=" * 86)

    # 1. date zilnice (doar când s-a închis o zi nouă)
    if not offline and not date_la_zi():
        print("📥 Zi nouă închisă -> actualizez datele...")
        try:
            actualizeaza_tot()
        except Exception as e:
            print(f"   ⚠️ Actualizare eșuată ({e}). Continuăm cu datele salvate.")

    df = incarca_date()
    inchise = calculeaza_indicatori(df[df['Inchisa']].reset_index(drop=True))
    ieri = inchise.iloc[-1]

    # 2. preț live
    pret, sursa = ieri['Close'], 'închiderea ultimei zile'
    if not offline:
        try:
            pret, sursa = pret_curent(), 'LIVE Binance'
        except Exception as e:
            print(f"   ⚠️ Preț live indisponibil ({e}); folosim ultima închidere.")

    stare = incarca_stare()
    if stare is None:
        stare = stare_noua(capital_start, pret)
        print(f"🆕 Portofoliu virtual nou: ${capital_start:,.2f} (BTC la ${pret:,.2f})")

    # 3. decizie pe zi închisă (o singură dată pe zi)
    zi = ieri['Data']
    print(f"\n📊 Semnal pe ziua închisă {zi} (Close ${ieri['Close']:,.2f}):")
    print(f"   {explica(ieri)}")
    print(f"   Scor final: {ieri['Scor_Final']:.0%}  ->  ținta de expunere: "
          f"{tinta_noua(ieri['Scor_Final'], stare['tinta']):.0%}")

    if stare['ultima_zi_procesata'] == zi:
        print(f"   ✔️ Decizia pentru {zi} a fost deja luată. Următoarea la închiderea zilei (00:00 UTC).")
    else:
        noua = tinta_noua(ieri['Scor_Final'], stare['tinta'])
        if noua != stare['tinta']:
            executa(stare, noua, pret, zi, ieri)
        else:
            print(f"   ⏸️ HOLD - ținta rămâne {stare['tinta']:.0%} (schimbarea e sub pragul de {CONFIG['histerezis']:.0%}).")
        stare['ultima_zi_procesata'] = zi

    # 4. semnal provizoriu (ziua în curs, cu prețul live) - informativ
    if not offline and not df['Inchisa'].iloc[-1]:
        azi = df.copy()
        azi.loc[azi.index[-1], 'Close'] = pret
        prov = calculeaza_indicatori(azi).iloc[-1]
        t_prov = tinta_noua(prov['Scor_Final'], stare['tinta'])
        semn = '(fără schimbare)' if t_prov == stare['tinta'] else '⚠️ s-ar schimba!'
        print(f"\n🔮 Provizoriu, dacă ziua s-ar închide acum la ${pret:,.0f}: scor {prov['Scor_Final']:.0%} "
              f"-> ținta {t_prov:.0%} {semn}")

    # 5. portofoliu
    valoare = stare['cash'] + stare['btc'] * pret
    bh = stare['capital_initial'] * pret / stare['pret_la_pornire']
    expunere = stare['btc'] * pret / valoare if valoare else 0
    print("\n" + "-" * 86)
    print(f" 💼 PORTOFOLIU VIRTUAL  (pornit {stare['pornit_la']}, BTC atunci ${stare['pret_la_pornire']:,.0f})")
    print("-" * 86)
    print(f"   Preț BTC ({sursa}): ${pret:,.2f}  |  RSI14 {ieri['RSI_14']:.0f}  |  "
          f"Volatilitate 30z {ieri['Volatilitate_30d']:.0%}  |  sub ATH {ieri['Drawdown_ATH']:.0%}")
    print(f"   💵 Cash ${stare['cash']:,.2f}  |  🪙 BTC {stare['btc']:.6f} (${stare['btc'] * pret:,.2f})  |  expunere {expunere:.0%}")
    print(f"   💰 Valoare ${valoare:,.2f}  |  P/L {valoare / stare['capital_initial'] - 1:+.2%}  |  "
          f"Buy&Hold de la pornire {bh / stare['capital_initial'] - 1:+.2%}")
    print(f"   🧾 Tranzacții {stare['nr_tranzactii']}  |  comisioane ${stare['comisioane']:,.2f}  |  jurnal: {JURNAL.name}")

    salveaza_stare(stare)


def main():
    p = argparse.ArgumentParser(description='AI Hedge Fund - simulator live (paper trading)')
    p.add_argument('--capital', type=float, default=10000.0)
    p.add_argument('--interval', type=float, default=15, help='minute între cicluri')
    p.add_argument('--o-data', action='store_true', help='un singur ciclu')
    p.add_argument('--offline', action='store_true')
    p.add_argument('--reset', action='store_true')
    a = p.parse_args()

    if a.reset:
        for f in (STARE, JURNAL):
            if f.exists():
                f.rename(f.with_name(f"{f.stem}_arhivat_{datetime.now():%Y%m%d_%H%M%S}{f.suffix}"))
        print("♻️ Portofoliul virtual a fost resetat (fișierele vechi au fost arhivate, nu șterse).")

    if a.o_data:
        ciclu(a.capital, a.offline)
        return

    print(f"[🔄] Simulator pornit: ciclu la {a.interval:g} minute. Ctrl+C pentru oprire.")
    try:
        while True:
            try:
                ciclu(a.capital, a.offline)
            except Exception as e:  # un ciclu ratat nu trebuie să oprească simulatorul
                print(f"❌ Eroare în ciclu: {e}")
            urm = datetime.fromtimestamp(time.time() + a.interval * 60).strftime('%H:%M:%S')
            print(f"\n[💤] Următorul ciclu la {urm}")
            time.sleep(a.interval * 60)
    except KeyboardInterrupt:
        print("\n[!] Simulator oprit. Starea e salvată în stare_live.json.")


if __name__ == "__main__":
    main()
