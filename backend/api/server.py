"""
J.A.R.V.I.S. - server API pentru interfața web (frontend/).

Expune datele existente ale proiectului, FĂRĂ să dubleze logica strategiilor:
  GET  /api/piata        preț live Binance + Master_Index și componentele lui
  GET  /api/sdca         portofoliul botului SDCA v2 + ce ar decide azi
  GET  /api/ai           simulatorul AI Hedge Fund: portofoliu, cele 12 voturi, jurnal
  GET  /api/istoric      serii pentru grafice (preț, Master_Index)
  GET  /api/backtest     curbele de capital SDCA v2 vs AI vs Buy & Hold (aceeași perioadă)
  POST /api/backtest/sdca, /api/backtest/ai   backtest la cerere (start, capital), cu jurnal complet
  GET  /api/heatmap      heatmap estimat al lichidărilor din Open Interest Binance (?interval=15m|1h|4h)
  GET  /api/stiri        știri despre Bitcoin, aur, S&P 500, piețe (RSS public) + cotații
  GET  /api/boti         starea boților live; POST /api/boti/<bot>/porneste|opreste|ciclu|reseteaza
  GET  /api/boti/<bot>/log    ultimele linii din log-ul botului
  POST /api/actualizeaza descarcă date noi (pipeline + date AI), în fundal
  GET  /api/status       versiunea datelor + starea actualizării automate (pipeline la 60 min, AI zilnic)
  POST /api/chat         asistentul - se activează în etapa finală (cheie Anthropic)

Pornire (din folderul proiectului):
  venv\\Scripts\\python.exe backend\\api\\server.py      ->  http://127.0.0.1:8000
"""
import copy
import json
import math
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional

API_DIR = Path(__file__).resolve().parent
BACKEND_DIR = API_DIR.parent
PROIECT_DIR = BACKEND_DIR.parent
FRONTEND_DIR = PROIECT_DIR / 'frontend'
for sub in ('pipeline', 'strategii/sdca', 'strategii/ai_hedgefund'):
    sys.path.insert(0, str(BACKEND_DIR / sub))

from cai import DATA_DIR  # noqa: E402
from data_loader import incarca_dataset  # noqa: E402
import strategie_sdca as sdca  # noqa: E402
import backtest_sdca_long as bt_sdca  # noqa: E402
import date_ai  # noqa: E402
import strategie_ai  # noqa: E402
import backtest_ai  # noqa: E402
import bot_live_ai  # noqa: E402
import control_boti  # noqa: E402
import heatmap_oi  # noqa: E402
import stiri  # noqa: E402

SDCA_STARE = BACKEND_DIR / 'strategii' / 'sdca' / 'bot_state.json'
START_COMPARATIE = bt_sdca.START_IMPLICIT   # prima zi cu toate datele on-chain
CAPITAL_COMPARATIE = 10000.0

PONDERI = {'Z_VWAP': 0.10, 'Z_MACD': 0.10, 'Z_RSI': 0.10, 'Z_Funding_Rate': 0.15, 'Adjusted_MVRV': 0.20, 'Z_SOPR': 0.20}
NUME_COMPONENTE = {'Z_VWAP': 'VWAP', 'Z_MACD': 'MACD', 'Z_RSI': 'RSI', 'Z_Funding_Rate': 'Funding',
                   'Adjusted_MVRV': 'MVRV ajustat', 'Z_SOPR': 'STH-SOPR'}

app = FastAPI(title="J.A.R.V.I.S. BTC Quant Terminal")


# ----------------------------------------------------------------------------- utilitare
def curat(o):
    """Transformă rezultatul în JSON valid (numpy -> python, NaN/inf -> null)."""
    if isinstance(o, dict):
        return {str(k): curat(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [curat(v) for v in o]
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating, float)):
        f = float(o)
        return None if math.isnan(f) or math.isinf(f) else f
    if isinstance(o, (np.bool_,)):
        return bool(o)
    return o


class Cache:
    """Cache simplu în memorie: valoare + expirare (sec) + o cheie care o invalidează (ex. mtime fișiere)."""
    def __init__(self):
        self.date = {}

    def ia(self, nume, ttl, cheie, functie):
        intrare = self.date.get(nume)
        if intrare and time.time() - intrare['t'] < ttl and intrare['cheie'] == cheie:
            return intrare['v']
        v = functie()
        self.date[nume] = {'v': v, 't': time.time(), 'cheie': cheie}
        return v


cache = Cache()


def mtime(*cai):
    return tuple(p.stat().st_mtime if p.exists() else 0 for p in cai)


def binance_24h():
    def _f():
        try:
            r = requests.get("https://api.binance.com/api/v3/ticker/24hr", params={"symbol": "BTCUSDT"}, timeout=10).json()
            return {'pret': float(r['lastPrice']), 'variatie_24h': float(r['priceChangePercent']),
                    'max_24h': float(r['highPrice']), 'min_24h': float(r['lowPrice']),
                    'volum_24h_usd': float(r['quoteVolume']), 'sursa': 'LIVE Binance', 'ok': True}
        except Exception as e:
            return {'ok': False, 'eroare': str(e)}
    return cache.ia('binance24h', 15, None, _f)


def master():
    p = DATA_DIR / 'master_dataset.csv'
    return cache.ia('master', 3600, mtime(p), lambda: sdca.adauga_indicatori(incarca_dataset()))


def date_ai_inchise():
    fis = (date_ai.DATA_DIR / 'btc_1d.csv', date_ai.DATA_DIR / 'funding_1d.csv')
    def _f():
        df = date_ai.incarca_date()
        return strategie_ai.calculeaza_indicatori(df[df['Inchisa']].reset_index(drop=True))
    return cache.ia('ai_ind', 3600, mtime(*fis), _f)


def citeste_json(p):
    try:
        return json.loads(p.read_text(encoding='utf-8')) if p.exists() else None
    except Exception:
        return None


# ----------------------------------------------------------------------------- piață
@app.get("/api/piata")
def piata():
    m = master()
    azi = m.iloc[-1]
    live = binance_24h()
    pret = live['pret'] if live.get('ok') else float(azi['Close'])
    componente = [{'cheie': k, 'nume': NUME_COMPONENTE[k], 'valoare': azi.get(k), 'pondere': w,
                   'contributie': (azi.get(k) or 0) * w} for k, w in PONDERI.items()]
    zi_utc = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    return curat({
        'pret': pret, 'live': live,
        'master': {'data': azi['Data'], 'valoare': azi['Master_Index'], 'semnal': azi['Semnal'],
                   'prag_buy': -0.5, 'prag_sell': 0.8, 'componente': componente,
                   'data_onchain': azi.get('Data_OnChain'), 'rsi': azi.get('RSI'),
                   'z_open_interest': azi.get('Z_Open_Interest')},
        'prospetime': {'master_zi': azi['Data'], 'azi_utc': zi_utc, 'la_zi': azi['Data'] >= zi_utc,
                       'onchain_zi': azi.get('Data_OnChain')},
        'ora_server': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    })


# ----------------------------------------------------------------------------- SDCA
@app.get("/api/sdca")
def sdca_status():
    m = master()
    azi = m.iloc[-1]
    live = binance_24h()
    pret = live['pret'] if live.get('ok') else float(azi['Close'])
    stare = citeste_json(SDCA_STARE)

    # Ce ar face botul azi: rulăm decizia pe o COPIE a stării (nu modificăm nimic).
    baza = copy.deepcopy(stare) if stare else sdca.stare_noua(CAPITAL_COMPARATIE)
    if stare and stare.get('ultima_rulare') == azi['Data']:
        previzualizare = {'mesaje': [], 'nota': f"Decizia pentru {azi['Data']} a fost deja luată de bot."}
    else:
        mesaje = sdca.decide(baza, azi)
        previzualizare = {'mesaje': mesaje,
                          'nota': 'Simulare pe o copie a portofoliului' + ('' if stare else ' (portofoliu nou de $10.000)')}

    portofoliu = None
    if stare:
        valoare = stare['cash'] + stare['btc'] * pret
        portofoliu = {'cash': stare['cash'], 'btc': stare['btc'], 'valoare': valoare,
                      'capital_initial': stare['capital_initial'],
                      'pl_procent': (valoare / stare['capital_initial'] - 1) * 100,
                      'pret_mediu': stare['total_investit'] / stare['btc'] if stare['btc'] > 0 else None,
                      'ultima_rulare': stare.get('ultima_rulare'),
                      'flaguri': {k: stare.get(k) for k in ('profit_lock_activ', 'interdictie_macro_activa',
                                                            'alerta_rosie_euforie', 'distributie_finala_activa')}}
    dd = (azi['Cycle_Peak_90d'] - azi['Close']) / azi['Cycle_Peak_90d']
    return curat({'pret': pret, 'portofoliu': portofoliu, 'initializat': stare is not None,
                  'previzualizare': previzualizare,
                  'context': {'master_index': azi['Master_Index'], 'mvrv_ajustat': azi['Adjusted_MVRV'],
                              'prag_mvrv_top': sdca.PRAG_MVRV_TOP, 'sma_50': azi['SMA_50'],
                              'varf_90z': azi['Cycle_Peak_90d'], 'sub_varf_90z': dd, 'zi': azi['Data']}})


# ----------------------------------------------------------------------------- AI Hedge Fund
@app.get("/api/ai")
def ai_status():
    ind = date_ai_inchise()
    ieri = ind.iloc[-1]
    cfg = strategie_ai.CONFIG
    stare = citeste_json(bot_live_ai.STARE)
    live = binance_24h()
    pret = live['pret'] if live.get('ok') else float(ieri['Close'])
    tinta_curenta = stare['tinta'] if stare else 0.0

    voturi = ([{'grup': 'trend', 'nume': f'SMA {n}', 'da': bool(ieri[f'V_trend_{n}'])} for n in cfg['sma_orizonturi']] +
              [{'grup': 'momentum', 'nume': f'Mom {n}z', 'da': bool(ieri[f'V_mom_{n}'])} for n in cfg['mom_orizonturi']])
    portofoliu = None
    if stare:
        valoare = stare['cash'] + stare['btc'] * pret
        portofoliu = {'cash': stare['cash'], 'btc': stare['btc'], 'valoare': valoare,
                      'capital_initial': stare['capital_initial'], 'tinta': stare['tinta'],
                      'expunere': stare['btc'] * pret / valoare if valoare else 0,
                      'pl_procent': (valoare / stare['capital_initial'] - 1) * 100,
                      'buyhold_procent': (pret / stare['pret_la_pornire'] - 1) * 100,
                      'pornit_la': stare['pornit_la'], 'nr_tranzactii': stare['nr_tranzactii'],
                      'comisioane': stare['comisioane'], 'ultima_zi_procesata': stare['ultima_zi_procesata']}
    jurnal = []
    if bot_live_ai.JURNAL.exists():
        jurnal = pd.read_csv(bot_live_ai.JURNAL).tail(15).iloc[::-1].to_dict('records')
    return curat({'pret': pret, 'zi_semnal': ieri['Data'], 'voturi': voturi,
                  'scor_trend': ieri['Scor_Trend'], 'scor_momentum': ieri['Scor_Momentum'],
                  'scor_final': ieri['Scor_Final'], 'funding_7d': ieri['Funding_7d'],
                  'funding_fierbinte': bool(ieri['Funding_Fierbinte']), 'prag_funding': cfg['funding_prag'],
                  'tinta_maine': strategie_ai.tinta_noua(ieri['Scor_Final'], tinta_curenta),
                  'rsi': ieri['RSI_14'], 'volatilitate_30z': ieri['Volatilitate_30d'], 'sub_ath': ieri['Drawdown_ATH'],
                  'portofoliu': portofoliu, 'initializat': stare is not None, 'jurnal': jurnal})


# ----------------------------------------------------------------------------- grafice
@app.get("/api/istoric")
def istoric(zile: int = 365):
    m = master().tail(max(30, min(zile, 2000)))
    return curat({'data': m['Data'].tolist(), 'pret': m['Close'].round(2).tolist(),
                  'master': m['Master_Index'].round(3).tolist(), 'prag_buy': -0.5, 'prag_sell': 0.8})


@app.get("/api/backtest")
def backtest():
    fis = (DATA_DIR / 'master_dataset.csv', date_ai.DATA_DIR / 'btc_1d.csv', date_ai.DATA_DIR / 'funding_1d.csv')
    return cache.ia('backtest', 6 * 3600, mtime(*fis), _calculeaza_backtest)


def _calculeaza_backtest():
    m = master()
    end = '2100-01-01'
    eq_s, tr_s, ev_s, com_s, _ = bt_sdca.simuleaza(m, START_COMPARATIE, end, CAPITAL_COMPARATIE, v2=True)
    tr_a, eq_a = backtest_ai.ruleaza_backtest(date_ai_inchise(), START_COMPARATIE, end, CAPITAL_COMPARATIE)
    bh = bt_sdca.buy_hold(m, START_COMPARATIE, end, CAPITAL_COMPARATIE)

    df = pd.DataFrame({'Data': eq_s.index, 'sdca': eq_s.values, 'bh': bh.values}) \
        .merge(eq_a[['Data', 'Valoare']].rename(columns={'Valoare': 'ai'}), on='Data', how='inner')
    serii = {k: pd.Series(df[k].values) for k in ('sdca', 'ai', 'bh')}
    stat = {}
    for k, s in serii.items():
        st = bt_sdca.statistici(s)
        stat[k] = {'final': st['Final'], 'total': st['Total'] * 100, 'cagr': st['CAGR'] * 100,
                   'max_dd': st['MaxDD'] * 100, 'sharpe': st['Sharpe']}
    stat['sdca']['tranzactii'] = len(tr_s)
    stat['ai']['tranzactii'] = len(tr_a)
    stat['bh']['tranzactii'] = 1
    marcaje = [{'data': r['Data'], 'tip': r['Tip'], 'motiv': r['Motiv'], 'suma': r['Suma_USD'], 'pret': r['Pret']}
               for _, r in tr_s.iterrows() if r['Motiv'] in ('FRONT-LOAD MASIV', 'MACRO TOP 70%', 'MOONBAG FOMO', 'MOONBAG PANIC', 'RĂSCUMPĂRARE')]
    return curat({'start': df['Data'].iloc[0], 'end': df['Data'].iloc[-1], 'capital': CAPITAL_COMPARATIE,
                  'data': df['Data'].tolist(), 'sdca': df['sdca'].round(2).tolist(), 'ai': df['ai'].round(2).tolist(),
                  'bh': df['bh'].round(2).tolist(), 'statistici': stat, 'marcaje_sdca': marcaje})


# ----------------------------------------------------------------------------- actualizare date
# Actualizare AUTOMATĂ în fundal (cât timp serverul rulează):
#   - pipeline-ul Master_Index (preț, indicatori, funding, on-chain) dacă datele sunt mai vechi de 60 min
#     (BGeometrics rămâne descărcat cel mult o dată pe zi, prin cache)
#   - istoricul zilnic AI (Binance 2017+) la fiecare zi nouă închisă (00:00 UTC)
# Dacă botul respectiv rulează deja, el își actualizează singur datele -> serverul nu se suprapune.
# Dezactivare: variabila de mediu JARVIS_AUTO_UPDATE=0.
AUTO_ACTIV = os.environ.get('JARVIS_AUTO_UPDATE', '1') != '0'
AUTO_VERIFICARE_SEC = 300
AUTO_PIPELINE_MIN = 60
_lock_actualizare = threading.Lock()
_actualizare = {'ruleaza': False, 'ultima': None, 'rezultat': None, 'sursa': None}
_auto = {'activ': AUTO_ACTIV, 'interval_pipeline_min': AUTO_PIPELINE_MIN, 'ultima_verificare': None,
         'urmatoarea_verificare': None, 'ultima_actualizare': None, 'ultimul_rezultat': None}


def _acum():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def _ruleaza_actualizarea(pipeline=True, ai=True, sursa='manual'):
    if not _lock_actualizare.acquire(blocking=False):
        return None                                   # deja în curs
    _actualizare.update(ruleaza=True, rezultat=None, sursa=sursa)
    rezultat = {'pipeline': None, 'date_ai': None, 'log': ''}
    try:
        if pipeline:
            r = subprocess.run([sys.executable, str(BACKEND_DIR / 'pipeline' / 'actualizeaza_date.py')],
                               capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=600,
                               env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})
            rezultat['pipeline'] = r.returncode == 0
            rezultat['log'] = (r.stdout or '')[-2500:]
        if ai:
            try:
                date_ai.actualizeaza_tot()
                rezultat['date_ai'] = True
            except Exception:
                rezultat['date_ai'] = False
        cache.date.clear()
    except Exception as e:
        rezultat.update(pipeline=False if pipeline else None, log=str(e))
    finally:
        _actualizare.update(ruleaza=False, ultima=_acum(), rezultat=rezultat)
        _lock_actualizare.release()
    return rezultat


def _bucla_auto():
    """Verifică la fiecare 5 minute dacă datele trebuie reîmprospătate."""
    time.sleep(5)   # lăsăm serverul să pornească
    while True:
        try:
            p = DATA_DIR / 'master_dataset.csv'
            vechime_min = (time.time() - p.stat().st_mtime) / 60 if p.exists() else 1e9
            pipeline = vechime_min > AUTO_PIPELINE_MIN and not control_boti.status('sdca')['ruleaza']
            ai = not bot_live_ai.date_la_zi() and not control_boti.status('ai')['ruleaza']
            _auto['ultima_verificare'] = _acum()
            if pipeline or ai:
                rez = _ruleaza_actualizarea(pipeline=pipeline, ai=ai, sursa='automat')
                if rez is not None:
                    _auto.update(ultima_actualizare=_acum(), ultimul_rezultat=rez)
        except Exception as e:
            _auto['ultimul_rezultat'] = {'eroare': str(e)}
        _auto['urmatoarea_verificare'] = datetime.fromtimestamp(time.time() + AUTO_VERIFICARE_SEC).strftime('%Y-%m-%d %H:%M:%S')
        time.sleep(AUTO_VERIFICARE_SEC)


@app.on_event("startup")
def porneste_auto():
    if AUTO_ACTIV:
        threading.Thread(target=_bucla_auto, daemon=True, name='jarvis-auto-update').start()


@app.post("/api/actualizeaza")
def actualizeaza():
    if not _actualizare['ruleaza']:
        threading.Thread(target=_ruleaza_actualizarea, daemon=True).start()
    return {'pornit': True}


@app.get("/api/actualizeaza")
def actualizeaza_status():
    return _actualizare


@app.get("/api/status")
def status_platforma():
    """Versiunea datelor: frontend-ul o verifică periodic și redesenează doar când s-a schimbat ceva."""
    fisiere = (DATA_DIR / 'master_dataset.csv', date_ai.DATA_DIR / 'btc_1d.csv', date_ai.DATA_DIR / 'funding_1d.csv',
               SDCA_STARE, bot_live_ai.STARE, bot_live_ai.JURNAL)
    versiune = format(abs(hash(mtime(*fisiere))), 'x')
    m = DATA_DIR / 'master_dataset.csv'
    return {'versiune_date': versiune, 'auto': _auto, 'actualizare': _actualizare,
            'master_actualizat': datetime.fromtimestamp(m.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S') if m.exists() else None,
            'boti': {b: control_boti.status(b)['ruleaza'] for b in control_boti.BOTI}}


# ----------------------------------------------------------------------------- heatmap lichidări (Open Interest)
@app.get("/api/heatmap")
def heatmap(interval: str = '1h'):
    if interval not in heatmap_oi.INTERVALE:
        raise HTTPException(422, f"Interval invalid. Alege: {', '.join(heatmap_oi.INTERVALE)}")
    try:
        return curat(cache.ia('heatmap_' + interval, 55, None, lambda: heatmap_oi.calculeaza(interval)))
    except Exception as e:
        raise HTTPException(502, f"Nu pot descărca datele Binance Futures: {e}")


# ----------------------------------------------------------------------------- știri de piață
@app.get("/api/stiri")
def stiri_piata():
    """Titluri despre Bitcoin, aur, S&P 500 și piețe + cotațiile celor trei instrumente (cache 5 minute)."""
    try:
        return curat(cache.ia('stiri', 300, None, lambda: {**stiri.stiri(), 'cotatii': stiri.cotatii()}))
    except Exception as e:
        raise HTTPException(502, f"Nu pot descărca știrile: {e}")


# ----------------------------------------------------------------------------- boți live (control)
class ComandaBot(BaseModel):
    capital: Optional[float] = None
    interval: Optional[float] = None


def _bot_valid(bot):
    if bot not in control_boti.BOTI:
        raise HTTPException(404, f"Bot necunoscut: {bot}")


def _executa(functie, *args):
    try:
        return curat(functie(*args))
    except ValueError as e:
        raise HTTPException(409, str(e))


@app.get("/api/boti")
def boti_status():
    return {b: control_boti.status(b) for b in control_boti.BOTI}


@app.post("/api/boti/{bot}/porneste")
def bot_porneste(bot: str, cmd: ComandaBot):
    _bot_valid(bot)
    return _executa(control_boti.porneste, bot, cmd.capital, cmd.interval)


@app.post("/api/boti/{bot}/opreste")
def bot_opreste(bot: str):
    _bot_valid(bot)
    return _executa(control_boti.opreste, bot)


@app.post("/api/boti/{bot}/ciclu")
def bot_ciclu(bot: str, cmd: ComandaBot):
    _bot_valid(bot)
    return _executa(control_boti.ciclu, bot, cmd.capital)


@app.post("/api/boti/{bot}/reseteaza")
def bot_reseteaza(bot: str):
    _bot_valid(bot)
    return _executa(control_boti.reseteaza, bot)


@app.get("/api/boti/{bot}/log")
def bot_log(bot: str, linii: int = 250):
    _bot_valid(bot)
    return {'linii': control_boti.log(bot, max(10, min(linii, 2000)))}


# ----------------------------------------------------------------------------- backtest la cerere
class CerereBacktest(BaseModel):
    start: str = START_COMPARATIE
    capital: float = 10000.0


def _valideaza(cerere, minim):
    try:
        start = pd.Timestamp(cerere.start).strftime('%Y-%m-%d')
    except Exception:
        raise HTTPException(422, "Data de start trebuie să fie de forma AAAA-LL-ZZ.")
    if not (10 <= cerere.capital <= 1e9):
        raise HTTPException(422, "Capitalul trebuie să fie între $10 și $1.000.000.000.")
    return max(start, minim), cerere.capital


def _pe_ani(date, valori, bh):
    df = pd.DataFrame({'Data': date, 'v': valori, 'bh': bh})
    df['An'] = df['Data'].str[:4]
    rez = []
    for an, g in df.groupby('An'):
        rez.append({'an': an, 'strategie': (g['v'].iloc[-1] / g['v'].iloc[0] - 1) * 100,
                    'buy_hold': (g['bh'].iloc[-1] / g['bh'].iloc[0] - 1) * 100,
                    'max_dd': (g['v'] / g['v'].cummax() - 1).min() * 100})
    return rez


def _statistici(serie):
    st = bt_sdca.statistici(pd.Series(list(serie)))
    return {'final': st['Final'], 'total': st['Total'] * 100, 'cagr': st['CAGR'] * 100,
            'max_dd': st['MaxDD'] * 100, 'sharpe': st['Sharpe']}


@app.post("/api/backtest/sdca")
def backtest_sdca(cerere: CerereBacktest):
    start, capital = _valideaza(cerere, START_COMPARATIE)
    m = master()
    eq, tr, ev, comisioane, st = bt_sdca.simuleaza(m, start, '2100-01-01', capital, v2=True)
    if len(eq) < 2:
        raise HTTPException(422, "Prea puține zile de date după data de start.")
    bh = bt_sdca.buy_hold(m, start, '2100-01-01', capital)
    pret_final = float(m['Close'].iloc[-1])
    vanzari = tr[tr['Tip'] == 'SELL'] if len(tr) else tr
    return curat({
        'start': eq.index[0], 'end': eq.index[-1], 'capital': capital,
        'statistici': {'strategie': _statistici(eq.values), 'buy_hold': _statistici(bh.values)},
        'final': {'cash': st['cash'], 'btc': st['btc'], 'valoare_btc': st['btc'] * pret_final,
                  'pret_mediu': st['total_investit'] / st['btc'] if st['btc'] > 0 else None,
                  'profit_realizat': float(vanzari['Profit_realizat'].sum()) if len(vanzari) else 0.0,
                  'profit_nerealizat': (st['btc'] * pret_final - st['total_investit']) if st['btc'] > 0 else 0.0,
                  'comisioane': comisioane, 'nr_cumparari': int((tr['Tip'] == 'BUY').sum()) if len(tr) else 0,
                  'nr_vanzari': len(vanzari)},
        'serii': {'data': list(eq.index), 'strategie': [round(v, 2) for v in eq.values],
                  'buy_hold': [round(v, 2) for v in bh.values]},
        'pe_ani': _pe_ani(list(eq.index), eq.values, bh.values),
        'tranzactii': tr.to_dict('records') if len(tr) else [],
        'evenimente': ev.to_dict('records') if len(ev) else [],
    })


@app.post("/api/backtest/ai")
def backtest_ai_endpoint(cerere: CerereBacktest):
    ind = date_ai_inchise()
    prima = ind[ind['Valid']]['Data'].iloc[0]
    start, capital = _valideaza(cerere, prima)
    tr, eq = backtest_ai.ruleaza_backtest(ind, start, '2100-01-01', capital)
    if len(eq) < 2:
        raise HTTPException(422, "Prea puține zile de date după data de start.")
    tranzactii = []
    for r in tr.to_dict('records'):
        if r['Funding_fierbinte']:
            motiv = (f"{r['Scor'] * 2:.0%} din cei 12 experți (trend + momentum) văd trend ascendent, dar funding-ul e "
                     f"fierbinte (long-uri supra-îndatorate) → scor înjumătățit la {r['Scor']:.0%}")
        else:
            motiv = f"{r['Scor']:.0%} din cei 12 experți (trend + momentum) văd trend ascendent"
        motiv += f" → expunerea țintă trece din {r['Expunere_veche']:.0%} în {r['Expunere_noua']:.0%}"
        tranzactii.append({**r, 'De_ce': motiv})
    cost = strategie_ai.CONFIG['comision'] + strategie_ai.CONFIG['slippage']
    return curat({
        'start': eq['Data'].iloc[0], 'end': eq['Data'].iloc[-1], 'capital': capital, 'prima_zi_posibila': prima,
        'statistici': {'strategie': _statistici(eq['Valoare']), 'buy_hold': _statistici(eq['BuyHold'])},
        'final': {'expunere_medie': float(eq['Expunere'].mean()), 'expunere_finala': float(eq['Expunere'].iloc[-1]),
                  'comisioane': float(tr['Suma_USD'].sum() * cost) if len(tr) else 0.0,
                  'nr_tranzactii': len(tr)},
        'serii': {'data': eq['Data'].tolist(), 'strategie': eq['Valoare'].round(2).tolist(),
                  'buy_hold': eq['BuyHold'].round(2).tolist(), 'expunere': eq['Expunere'].tolist()},
        'pe_ani': _pe_ani(eq['Data'].tolist(), eq['Valoare'].values, eq['BuyHold'].values),
        'tranzactii': tranzactii,
    })


# ----------------------------------------------------------------------------- asistent (etapa finală)
@app.post("/api/chat")
def chat():
    raise HTTPException(status_code=503, detail="Asistentul J.A.R.V.I.S. nu este încă activat. "
                                                "Se conectează în etapa finală, cu cheia API Anthropic.")


# ----------------------------------------------------------------------------- frontend
@app.get("/")
def index():
    return FileResponse(FRONTEND_DIR / 'index.html')


app.mount("/", StaticFiles(directory=FRONTEND_DIR), name="frontend")


if __name__ == "__main__":
    import socket
    import webbrowser
    import uvicorn

    URL = "http://127.0.0.1:8000"
    deschide = '--deschide' in sys.argv     # deschide singur browserul (folosit de porneste_jarvis.bat)

    # Dacă platforma rulează deja (altă fereastră), nu pornim a doua oară: doar deschidem pagina.
    with socket.socket() as s:
        s.settimeout(0.5)
        if s.connect_ex(('127.0.0.1', 8000)) == 0:
            print(f"J.A.R.V.I.S. rulează deja pe {URL}")
            if deschide:
                webbrowser.open(URL)
            sys.exit(0)

    def adresa_telefon():
        """Adresa din rețeaua privată Tailscale (dacă platforma e publicată cu `tailscale serve --bg 8000`)."""
        import re
        import shutil
        exe = shutil.which('tailscale') or r'C:\Program Files\Tailscale\tailscale.exe'
        try:
            r = subprocess.run([exe, 'serve', 'status'], capture_output=True, text=True, timeout=5)
            m = re.search(r'https://[\w.-]+\.ts\.net', r.stdout or '')
            return m.group(0) if m else None
        except Exception:
            return None

    print("=" * 64)
    print(f" J.A.R.V.I.S. pornește pe {URL}")
    telefon = adresa_telefon()
    if telefon:
        print(f" Pe telefon (cu Tailscale conectat): {telefon}")
    print(" Lasă fereastra deschisă cât folosești platforma. Ctrl+C = oprire.")
    print("=" * 64)
    if deschide:
        threading.Timer(2.5, lambda: webbrowser.open(URL)).start()
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")
