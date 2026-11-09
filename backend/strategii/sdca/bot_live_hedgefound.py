import pandas as pd
import os
import json
import time
import sys
import argparse
import subprocess
from datetime import datetime
import warnings
from pathlib import Path

SDCA_DIR = Path(__file__).resolve().parent
PIPELINE_DIR = SDCA_DIR.parent.parent / 'pipeline'
sys.path.insert(0, str(PIPELINE_DIR))
from data_loader import incarca_dataset  # noqa: E402
from strategie_sdca import stare_noua, adauga_indicatori, decide  # noqa: E402  (logica comună cu backtest-ul)

warnings.filterwarnings('ignore')

STATE_FILE = SDCA_DIR / 'bot_state.json'
REPLAY_STATE_FILE = SDCA_DIR / 'bot_state_replay.json'  # replay-ul nu atinge portofoliul real
NUME_SCRIPT_DATE = PIPELINE_DIR / 'actualizeaza_date.py'

# Moduri de rulare (din folderul proiectului):
#   python backend/strategii/sdca/bot_live_hedgefound.py                      -> LIVE: date noi + decizie, la 3 ore
#   python backend/strategii/sdca/bot_live_hedgefound.py --offline            -> o analiză pe datele locale
#   python backend/strategii/sdca/bot_live_hedgefound.py --replay 2025-01-01  -> rejoacă istoricul zi cu zi
#        opțional: --capital 10000  --pauza 0.3  (secunde între zile)


def actualizeaza_datele_live():
    """Rulează pipeline/actualizeaza_date.py. Returnează True dacă datele critice (preț + fuziune) s-au actualizat."""
    print(f"\n[🕒 {datetime.now().strftime('%H:%M:%S')}] Se inițiază actualizarea datelor din '{NUME_SCRIPT_DATE.name}'...")
    try:
        # sys.executable forțează utilizarea Python-ului din (venv)
        rezultat = subprocess.run([sys.executable, str(NUME_SCRIPT_DATE)], capture_output=True, text=True,
                                  encoding='utf-8', errors='replace',
                                  env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})

        print("\n--- LOG SCRIPT DATE ---")
        if rezultat.stdout:
            print(rezultat.stdout)
        if rezultat.stderr:
            print("[ERORI]:", rezultat.stderr)
        print("-----------------------")

        if rezultat.returncode == 0:
            return True
        print(f"[!] Actualizarea datelor CRITICE a eșuat (Cod: {rezultat.returncode}).")
        return False

    except Exception as e:
        print(f"[!] Eroare fatală la apelarea scriptului: {e}")
        return False

def incarca_memoria(cale=STATE_FILE):
    if os.path.exists(cale):
        with open(cale, 'r') as f:
            return json.load(f)
    return None

def salveaza_memoria(state, cale=STATE_FILE):
    with open(cale, 'w') as f:
        json.dump(state, f, indent=4)

def cere_capital():
    while True:
        try:
            capital = float(input("[?] Ce capital inițial investim? (Ex: 10000): $"))
            if capital > 0: return capital
            print("Sumă invalidă.")
        except ValueError:
            print("Valoare invalidă.")

def afiseaza_portofoliu(state, pret):
    valoare = state["cash"] + (state["btc"] * pret)
    print("\n" + "="*80)
    print(" 💼 REZUMAT PORTOFOLIU")
    print("="*80)
    print(f"💵 Cash: ${state['cash']:,.2f} | 🪙 BTC: {state['btc']:.4f} (${(state['btc'] * pret):,.2f})")
    print(f"💰 Valoare Totală: ${valoare:,.2f} | 📈 P/L: {((valoare/state['capital_initial'])-1)*100:.2f}%")
    print("="*80)

def rulare_ciclu_analiza(offline=False):
    mod = "OFFLINE (date locale)" if offline else "LIVE EXECUTION"
    print("\n" + "="*80)
    print(f" 🚀 HEDGE FUND AI - {mod} ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')}) 🚀")
    print("="*80)

    # 1. Update Date
    if offline:
        print("\n[i] Mod offline: nu se descarcă nimic, folosim backend/data/master_dataset.csv existent.")
    elif not actualizeaza_datele_live():
        print("[!] Nu decidem pe date neactualizate. Se reîncearcă la următorul ciclu.")
        return

    # 2. Încărcare Memorie
    state = incarca_memoria()
    if state is None:
        print("\n[i] Inițializare Portofoliu Nou.")
        state = stare_noua(cere_capital())
        salveaza_memoria(state)

    # 3. Procesare Date
    df = incarca_dataset()
    if df is None or df.empty:
        print("[!] Date indisponibile. Se reîncearcă la următorul ciclu.")
        return

    azi = adauga_indicatori(df).iloc[-1]
    print(f"\n📈 Situația pieței ({azi['Data']}):")
    print(f"   Preț BTC: ${azi['Close']:,.2f} | Z-Score: {azi['Master_Index']:+.2f}")

    zi_calendar = datetime.now().strftime('%Y-%m-%d')
    if azi['Data'] < zi_calendar:
        print(f"   [!] Atenție: ultimele date sunt din {azi['Data']}, nu din {zi_calendar}."
              + ("" if offline else " Verifică log-ul de actualizare."))

    print("\n🔍 ANALIZĂ ȘI DECIZII:")
    mesaje = decide(state, azi)
    for m in mesaje: print(m)
    if not mesaje:
        print("   ⏳ Status: STANDBY (Nu s-au îndeplinit condițiile de execuție).")

    salveaza_memoria(state)
    afiseaza_portofoliu(state, azi['Close'])

def replay_mode(start, capital, pauza):
    """
    Rejoacă istoricul din backend/data/master_dataset.csv zi cu zi, ca și cum botul ar fi rulat live.
    Nu are nevoie de internet și nu atinge bot_state.json (folosește bot_state_replay.json).
    """
    df = incarca_dataset()
    if df is None or df.empty:
        return
    # Indicatorii sunt toți rolling (folosesc doar trecutul), deci îi putem calcula o singură dată.
    df = adauga_indicatori(df)
    zile = df[df['Data'] >= start]
    if zile.empty:
        print(f"[!] Nu există date după {start}. Datele disponibile: {df['Data'].iloc[0]} -> {df['Data'].iloc[-1]}")
        return

    state = stare_noua(capital)
    print("\n" + "="*80)
    print(f" ⏪ REPLAY {zile['Data'].iloc[0]} -> {zile['Data'].iloc[-1]} | Capital ${capital:,.0f} | {len(zile)} zile")
    print("="*80)

    try:
        for _, azi in zile.iterrows():
            mesaje = decide(state, azi)
            valoare = state["cash"] + state["btc"] * azi['Close']
            status = " || ".join(mesaje) if mesaje else "standby"
            print(f"{azi['Data']} | ${azi['Close']:>10,.0f} | Z {azi['Master_Index']:+.2f} | "
                  f"Portofoliu ${valoare:>12,.0f} | {status}")
            salveaza_memoria(state, REPLAY_STATE_FILE)
            if pauza > 0:
                time.sleep(pauza)
    except KeyboardInterrupt:
        print("\n[!] Replay oprit manual.")

    afiseaza_portofoliu(state, azi['Close'])

def daemon_mode():
    ore_interval = 3
    secunde_interval = ore_interval * 3600

    print(f"\n[🔄] Modul AUTONOM activat. Botul se va actualiza din {ore_interval} în {ore_interval} ore.")
    print("[!] Apăsați CTRL+C pentru a opri execuția.\n")

    while True:
        rulare_ciclu_analiza()

        timp_urmator = datetime.fromtimestamp(time.time() + secunde_interval).strftime('%H:%M:%S')
        print(f"\n[💤] Botul intră în repaus. Următoarea rulare automată va fi la ora: {timp_urmator}")

        # Așteaptă 3 ore
        time.sleep(secunde_interval)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Hedge Fund AI - bot BTC")
    parser.add_argument('--offline', action='store_true', help='o singură analiză pe datele locale, fără descărcare')
    parser.add_argument('--replay', metavar='YYYY-MM-DD', help='rejoacă istoricul începând cu această dată')
    parser.add_argument('--capital', type=float, default=10000.0, help='capital pentru replay (implicit 10000)')
    parser.add_argument('--pauza', type=float, default=0.0, help='secunde între zile în replay (ex. 0.3 pentru demo)')
    args = parser.parse_args()

    if args.replay:
        replay_mode(args.replay, args.capital, args.pauza)
    elif args.offline:
        rulare_ciclu_analiza(offline=True)
    else:
        daemon_mode()
