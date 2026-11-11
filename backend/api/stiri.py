"""
ȘTIRI DE PIAȚĂ pentru platforma J.A.R.V.I.S.: titluri despre Bitcoin, aur, S&P 500 și piețe în general.

Surse (fluxuri RSS publice, fără cheie API):
  - Google News (căutări pe subiect; dă și numele publicației)
  - Yahoo Finance (titluri pe simbol), CoinDesk, Cointelegraph, CNBC Markets
Cotații pentru aur și S&P 500: Yahoo Finance (chart JSON, neoficial, cu întârziere).

Se afișează doar titlul, publicația, ora și linkul către articolul original (fără conținutul articolului).
Dacă o sursă pică, celelalte merg mai departe; sursa căzută e raportată în răspuns.
"""
import html
import re
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import requests

UA = {'User-Agent': 'Mozilla/5.0 (JarvisQuantTerminal; proiect academic)'}
TIMEOUT = 12
MAX_PE_CATEGORIE = 40
VECHIME_MAX_ZILE = 3


def _google(interogare):
    return f"https://news.google.com/rss/search?q={interogare}&hl=en-US&gl=US&ceid=US:en"


# categorie -> [(nume sursă implicit, url)]
SURSE = {
    'btc': [('Google News', _google('bitcoin+when:1d')),
            ('CoinDesk', 'https://www.coindesk.com/arc/outboundfeeds/rss/'),
            ('Cointelegraph', 'https://cointelegraph.com/rss')],
    'aur': [('Google News', _google('gold+price+when:2d'))],
    'spx': [('Google News', _google('%22S%26P+500%22+when:2d')),
            ('Yahoo Finance', 'https://feeds.finance.yahoo.com/rss/2.0/headline?s=^GSPC&region=US&lang=en-US')],
    'piete': [('CNBC', 'https://www.cnbc.com/id/20910258/device/rss/rss.html'),
              ('Google News', _google('%22stock+market%22+OR+%22Wall+Street%22+when:1d'))],
}
NUME_CATEGORII = {'btc': 'Bitcoin', 'aur': 'Aur', 'spx': 'S&P 500', 'piete': 'Piețe'}

INSTRUMENTE = [('BTC-USD', 'Bitcoin', 'btc'), ('GC=F', 'Aur (futures)', 'aur'), ('^GSPC', 'S&P 500', 'spx')]


def _curata(text):
    text = html.unescape(re.sub(r'<[^>]+>', '', text or ''))
    return re.sub(r'\s+', ' ', text).strip()


def _citeste_flux(categorie, sursa_implicita, url):
    r = requests.get(url, headers=UA, timeout=TIMEOUT)
    r.raise_for_status()
    rezultate = []
    limita = datetime.now(timezone.utc) - timedelta(days=VECHIME_MAX_ZILE)
    for item in ET.fromstring(r.content).iter('item'):
        titlu, link = _curata(item.findtext('title')), (item.findtext('link') or '').strip()
        if not titlu or not link.startswith('http'):
            continue
        try:
            data = parsedate_to_datetime(item.findtext('pubDate') or '')
            if data.tzinfo is None:
                data = data.replace(tzinfo=timezone.utc)
            data = data.astimezone(timezone.utc)
        except (TypeError, ValueError):
            continue
        if data < limita:
            continue
        sursa = _curata(item.findtext('source')) or sursa_implicita
        if sursa and titlu.endswith(' - ' + sursa):          # Google News: "Titlu - Publicație"
            titlu = titlu[:-len(sursa) - 3].strip()
        rezultate.append({'titlu': titlu, 'sursa': sursa, 'link': link, 'categorie': categorie,
                          'data': data.strftime('%Y-%m-%dT%H:%M:%SZ')})
    return rezultate


def stiri():
    """Toate știrile, cele mai noi primele, fără duplicate. Întoarce și sursele care nu au răspuns."""
    sarcini = [(cat, nume, url) for cat, lista in SURSE.items() for nume, url in lista]
    toate, cazute = [], []
    with ThreadPoolExecutor(max_workers=len(sarcini)) as ex:
        viitoare = [(s, ex.submit(_citeste_flux, *s)) for s in sarcini]
        for (cat, nume, _), v in viitoare:
            try:
                toate.extend(sorted(v.result(), key=lambda x: x['data'], reverse=True)[:MAX_PE_CATEGORIE])
            except Exception as e:
                cazute.append(f"{nume} ({NUME_CATEGORII[cat]}): {type(e).__name__}")

    vazute, unice = set(), []
    for s in sorted(toate, key=lambda x: x['data'], reverse=True):
        cheie = re.sub(r'[^a-z0-9]', '', s['titlu'].lower())[:70]
        if cheie and cheie not in vazute:
            vazute.add(cheie)
            unice.append(s)
    return {'stiri': unice, 'categorii': NUME_CATEGORII, 'surse_cazute': cazute,
            'actualizat': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}


def _cotatie(simbol, nume, categorie):
    r = requests.get(f'https://query1.finance.yahoo.com/v8/finance/chart/{simbol}',
                     params={'range': '5d', 'interval': '1d'}, headers=UA, timeout=TIMEOUT)
    r.raise_for_status()
    rez = r.json()['chart']['result'][0]
    pret = rez['meta']['regularMarketPrice']
    # închiderea zilei anterioare = ultima lumânare dintr-o zi mai veche decât cea a ultimului preț
    # (Yahoo adaugă uneori la final o lumânare duplicat cu prețul curent)
    zi_curenta = datetime.fromtimestamp(rez['meta']['regularMarketTime'], timezone.utc).date()
    anterioare = [c for t, c in zip(rez.get('timestamp') or [], rez['indicators']['quote'][0]['close'])
                  if c is not None and datetime.fromtimestamp(t, timezone.utc).date() < zi_curenta]
    anterior = anterioare[-1] if anterioare else None
    return {'simbol': simbol, 'nume': nume, 'categorie': categorie, 'pret': pret,
            'variatie_pct': (pret / anterior - 1) * 100 if anterior else None,
            'ora': datetime.fromtimestamp(rez['meta']['regularMarketTime'], timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}


def cotatii():
    """Bitcoin, aur și S&P 500: ultimul preț și variația față de închiderea zilei anterioare."""
    rezultate = []
    with ThreadPoolExecutor(max_workers=len(INSTRUMENTE)) as ex:
        for (simbol, nume, cat), v in [(i, ex.submit(_cotatie, *i)) for i in INSTRUMENTE]:
            try:
                rezultate.append(v.result())
            except Exception as e:
                rezultate.append({'simbol': simbol, 'nume': nume, 'categorie': cat, 'pret': None,
                                  'variatie_pct': None, 'eroare': type(e).__name__})
    return rezultate


if __name__ == '__main__':
    d = stiri()
    print(f"{len(d['stiri'])} știri | surse căzute: {d['surse_cazute'] or 'niciuna'}")
    for cat in SURSE:
        print(f"  {NUME_CATEGORII[cat]}: {sum(s['categorie'] == cat for s in d['stiri'])}")
    for s in d['stiri'][:6]:
        print(f"  {s['data']} [{s['categorie']}] {s['sursa']}: {s['titlu'][:80]}")
    for c in cotatii():
        print(' ', c)
