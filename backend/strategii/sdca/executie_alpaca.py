"""
Execuție SDCA în contul de TEST Alpaca (paper trading) - oglindește portofoliul botului.

Botul rămâne singura sursă a deciziilor (strategie_sdca.decide, aceleași date și reguli).
Modulul doar aliniază poziția BTC din contul Alpaca la poziția din bot_state.json:
    diferență = BTC în bot - BTC în Alpaca  ->  ordin market BTC/USD pe diferență.
Sincronizarea prin diferență face execuția robustă: un ordin eșuat sau un ciclu ratat se
recuperează automat la ciclul următor, iar starea botului nu depinde de Alpaca.

Siguranță:
  - adresa e fixată pe paper-api.alpaca.markets: modulul NU poate tranzacționa pe un cont real;
  - trimite ordine doar dacă ALPACA_SINCRONIZARE=1 în .env (altfel doar afișează planul);
  - nu trimite nimic dacă există deja un ordin BTC/USD deschis (evită ordinele duble);
  - botul folosește doar capitalul lui ($10.000 virtuali), nu tot contul Alpaca.

Rulare manuală (din folderul proiectului):
    venv\\Scripts\\python.exe backend\\strategii\\sdca\\executie_alpaca.py            # cont + plan, fără ordine
    venv\\Scripts\\python.exe backend\\strategii\\sdca\\executie_alpaca.py --trimite  # execută planul acum
"""
import argparse
import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

SDCA_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SDCA_DIR.parent.parent / 'pipeline'))
import cai  # noqa: E402,F401  (încarcă .env)

URL_PAPER = 'https://paper-api.alpaca.markets/v2'   # fix: doar contul de test
SIMBOL = 'BTC/USD'
SIMBOL_POZITIE = 'BTCUSD'
ORDIN_MINIM_USD = 25.0   # Alpaca ia comisionul (~0,25%) în BTC: sub prag nu „vânăm” diferența de comision
JURNAL = SDCA_DIR / 'alpaca_jurnal.jsonl'
STATE_FILE = SDCA_DIR / 'bot_state.json'


def _antete():
    cheie, secret = os.environ.get('ALPACA_API_KEY', ''), os.environ.get('ALPACA_SECRET_KEY', '')
    if not cheie or not secret:
        raise RuntimeError('Lipsesc ALPACA_API_KEY / ALPACA_SECRET_KEY din .env')
    return {'APCA-API-KEY-ID': cheie, 'APCA-API-SECRET-KEY': secret}


def configurat():
    return bool(os.environ.get('ALPACA_API_KEY')) and bool(os.environ.get('ALPACA_SECRET_KEY'))


def sincronizare_activa():
    return configurat() and os.environ.get('ALPACA_SINCRONIZARE', '0').strip() == '1'


def _get(cale, **params):
    return requests.get(f'{URL_PAPER}{cale}', headers=_antete(), params=params or None, timeout=15)


def cont():
    r = _get('/account'); r.raise_for_status()
    return r.json()


def pozitie_btc():
    """Cantitatea BTC deținută în contul Alpaca (0 dacă nu există poziție)."""
    r = _get(f'/positions/{SIMBOL_POZITIE}')
    if r.status_code == 404:
        return 0.0
    r.raise_for_status()
    return float(r.json().get('qty', 0))


def ordine_deschise():
    r = _get('/orders', status='open', symbols=SIMBOL); r.raise_for_status()
    return r.json()


def _jurnal(eveniment):
    eveniment = {'timp': datetime.now(timezone.utc).isoformat(timespec='seconds'), **eveniment}
    with open(JURNAL, 'a', encoding='utf-8') as f:
        f.write(json.dumps(eveniment, ensure_ascii=False) + '\n')


def plan(btc_bot, pret):
    """Ce ordin ar alinia Alpaca la bot. Returnează dict cu 'actiune' = 'buy' / 'sell' / None."""
    btc_alpaca = pozitie_btc()
    dif = btc_bot - btc_alpaca
    p = {'btc_bot': btc_bot, 'btc_alpaca': btc_alpaca, 'diferenta': dif, 'pret': pret, 'actiune': None}
    if abs(dif) * pret < ORDIN_MINIM_USD:
        p['motiv'] = f'aliniat (diferență sub ${ORDIN_MINIM_USD:.0f})'
        return p
    if dif > 0:
        p.update(actiune='buy', qty=math.floor(dif * 1e8) / 1e8)
    else:
        p.update(actiune='sell', qty=math.floor(min(-dif, btc_alpaca) * 1e8) / 1e8)
    p['valoare_usd'] = p['qty'] * pret
    return p


def sincronizeaza(btc_bot, pret, trimite=None):
    """Aliniază Alpaca la bot. trimite=None -> după ALPACA_SINCRONIZARE din .env. Returnează mesaje text."""
    if trimite is None:
        trimite = sincronizare_activa()
    if not configurat():
        return []
    try:
        p = plan(btc_bot, pret)
        if p['actiune'] is None:
            return [f"   🦙 Alpaca: {p['motiv']} (bot {btc_bot:.6f} BTC = Alpaca {p['btc_alpaca']:.6f} BTC)"]
        text = (f"{'CUMPĂRARE' if p['actiune'] == 'buy' else 'VÂNZARE'} {p['qty']:.6f} BTC "
                f"(~${p['valoare_usd']:,.0f}) | bot {btc_bot:.6f} vs Alpaca {p['btc_alpaca']:.6f}")
        if not trimite:
            return [f"   🦙 Alpaca (doar plan, ALPACA_SINCRONIZARE=0): {text}"]
        if ordine_deschise():
            return ["   🦙 Alpaca: există un ordin BTC/USD deschis, aștept execuția lui (fără ordin nou)."]
        corp = {'symbol': SIMBOL, 'qty': f"{p['qty']:.8f}", 'side': p['actiune'], 'type': 'market',
                'time_in_force': 'gtc'}
        r = requests.post(f'{URL_PAPER}/orders', headers=_antete(), json=corp, timeout=15)
        if r.status_code >= 300:
            _jurnal({'tip': 'eroare', 'ordin': corp, 'http': r.status_code, 'raspuns': r.text[:300]})
            return [f"   ❌ Alpaca a refuzat ordinul ({r.status_code}): {r.text[:200]} — reîncerc la ciclul următor."]
        o = r.json()
        _jurnal({'tip': 'ordin', 'id': o.get('id'), 'ordin': corp, 'pret_referinta': pret, 'status': o.get('status')})
        return [f"   🦙 Alpaca: ordin trimis — {text} (status {o.get('status')})"]
    except Exception as e:  # Alpaca nu are voie să oprească botul
        _jurnal({'tip': 'eroare', 'mesaj': str(e)[:300]})
        return [f"   ❌ Alpaca indisponibil: {e} — reîncerc la ciclul următor."]


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description='Sincronizare SDCA -> cont de test Alpaca')
    ap.add_argument('--trimite', action='store_true', help='trimite ordinul acum (altfel doar planul)')
    args = ap.parse_args()
    c = cont()
    print(f"Cont {c['account_number']} | status {c['status']} | crypto {c.get('crypto_status')} | "
          f"cash ${float(c['cash']):,.2f} | equity ${float(c['equity']):,.2f}")
    state = json.loads(STATE_FILE.read_text(encoding='utf-8'))
    r = requests.get('https://api.binance.com/api/v3/ticker/price', params={'symbol': 'BTCUSDT'}, timeout=15)
    pret = float(r.json()['price'])
    print(f"Bot: {state['btc']:.6f} BTC + ${state['cash']:,.2f} cash | preț BTC ${pret:,.0f}")
    for m in sincronizeaza(state['btc'], pret, trimite=args.trimite):
        print(m)
