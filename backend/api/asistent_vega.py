"""
VEGA - asistentul platformei, prin Google Gemini (AI Studio, cheia GEMINI_API_KEY din .env).

Serverul îi dă la fiecare întrebare un instantaneu al platformei (piață, Master_Index, boți, tranzacții,
știri), iar modelul răspunde doar pe baza lui. Cheia rămâne pe server; browserul nu o vede.
"""
import json
import os
import time

import requests

URL = 'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent'
MODEL_IMPLICIT = 'gemini-3.8-flash'
MODEL_REZERVA = 'gemini-flash-lite-latest'   # folosit când modelul principal e supraîncărcat (503) sau peste cotă (429)
MAX_ISTORIC = 12          # ultimele mesaje din conversație trimise modelului
TIMEOUT_PRINCIPAL = 25    # secunde: un model supraîncărcat poate ține cererea mult; trecem repede pe rezervă

INSTRUCTIUNI = """Ești Vega, asistentul platformei VEGA: un sistem academic (lucrare de licență) de tranzacționare
cantitativă BTC, SIMULATĂ (paper trading). Răspunzi în limba română, concis și clar, ca un analist cantitativ.

Ce știi despre sistem:
- Master_Index = 0.10·(Z_VWAP+Z_MACD+Z_RSI) + 0.15·Z_Funding + 0.20·(MVRV ajustat + Z_SOPR). Sub -0.5 = zonă de
  acumulare (BUY), peste 0.8 = euforie (SELL). Datele on-chain (MVRV, SOPR) vin cu 7 zile întârziere (BGeometrics gratuit).
- Botul SDCA v2: acumulează treptat în zonele de subevaluare, vinde 70% la euforie confirmată de MVRV, apoi moonbag;
  răscumpără dacă piața capitulează ≥10% sub prețul de vânzare. Ciclu la 3 ore. Ordinele lui sunt copiate în contul
  de TEST Alpaca.
- Botul AI Hedge Fund: 12 voturi (6 trend SMA + 6 momentum); procentul de voturi DA = expunerea BTC în trepte de 25%,
  cu filtru de funding. Decide la închiderea zilei (00:00 UTC).

Reguli:
- Folosește DOAR datele din instantaneul primit pentru cifre (prețuri, indicatori, portofolii, tranzacții). Dacă o
  informație lipsește, spune că nu o ai; nu inventa.
- Explică deciziile boților prin regulile lor și prin valorile indicatorilor.
- Nu da sfaturi de investiții personalizate și nu spune utilizatorului ce să cumpere sau să vândă cu banii lui;
  poți explica ce indică modelele și ce ar face boții. Amintește la nevoie că totul e simulat.
- Fără markdown greu: paragrafe scurte, eventual liste simple cu „-”."""


ULTIMUL_MODEL = [None]   # modelul care a dat ultimul răspuns (principal sau rezervă)


def configurat():
    return bool(os.environ.get('GEMINI_API_KEY', '').strip())


def model():
    return os.environ.get('GEMINI_MODEL', MODEL_IMPLICIT).strip() or MODEL_IMPLICIT


def raspunde(intrebare, istoric, instantaneu):
    """istoric: [{'rol': 'tu'|'vega', 'text': ...}] (fără întrebarea curentă). Returnează textul răspunsului."""
    if not configurat():
        raise RuntimeError('Lipsește GEMINI_API_KEY în .env')
    continut = []
    for m in (istoric or [])[-MAX_ISTORIC:]:
        text = str(m.get('text', ''))[:4000]
        if text:
            continut.append({'role': 'model' if m.get('rol') == 'vega' else 'user', 'parts': [{'text': text}]})
    continut.append({'role': 'user', 'parts': [{'text':
        'INSTANTANEU PLATFORMĂ (JSON, date reale în acest moment):\n'
        + json.dumps(instantaneu, ensure_ascii=False, default=str)
        + '\n\nÎNTREBAREA UTILIZATORULUI:\n' + intrebare[:4000]}]})
    corp = {'systemInstruction': {'parts': [{'text': INSTRUCTIUNI}]}, 'contents': continut,
            'generationConfig': {'temperature': 0.4, 'maxOutputTokens': 1200}}

    ultima = None
    modele = list(dict.fromkeys([model(), MODEL_REZERVA])) + [MODEL_REZERVA]   # rezerva are și o a doua încercare
    for i, m in enumerate(modele):
        try:
            r = requests.post(URL.format(model=m), params={'key': os.environ['GEMINI_API_KEY'].strip()},
                              json=corp, timeout=TIMEOUT_PRINCIPAL if i < len(modele) - 1 else 90)
        except requests.Timeout:
            ultima = f'{m} nu a răspuns la timp.'
            continue
        if r.status_code in (429, 500, 503):
            ultima = f'Gemini e ocupat momentan ({r.status_code}). Încearcă din nou peste câteva secunde.'
            time.sleep(2 if i else 0.5)
            continue
        if not r.ok:
            try:
                detaliu = r.json()['error']['message']
            except Exception:
                detaliu = r.text[:300]
            raise RuntimeError(f'Gemini a refuzat cererea ({r.status_code}): {detaliu}')
        d = r.json()
        try:
            parti = d['candidates'][0]['content']['parts']
            ULTIMUL_MODEL[0] = m
            return ''.join(p.get('text', '') for p in parti if not p.get('thought')).strip() or '(răspuns gol)'
        except (KeyError, IndexError):
            motiv = d.get('promptFeedback', {}).get('blockReason') or d.get('candidates', [{}])[0].get('finishReason')
            raise RuntimeError(f'Gemini nu a dat un răspuns ({motiv}).')
    raise RuntimeError(ultima or 'Gemini indisponibil.')
