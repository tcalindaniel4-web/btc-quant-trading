# 📈 Licență – Sistem de tranzacționare cantitativă BTC

Sistem de analiză și tranzacționare simulată (paper trading) pentru Bitcoin, bazat pe date de piață,
derivate și on-chain. Conține două strategii independente, fiecare cu backtest și bot live.

## 📁 Structura proiectului
```
licenta crypto ai/
├── README.md                     ← acest fișier
├── requirements.txt              ← bibliotecile Python necesare
├── .env / .env.example           ← tokenul API (secret, nu intră în git) / model
├── .gitignore                    ← ce nu se versionează (venv, date generate, stări boți, .env)
├── venv/                         ← mediul virtual Python
│
├── backend/
│   ├── api/                      ← serverul platformei web J.A.R.V.I.S. (FastAPI)
│   │   ├── server.py                 API: piață, boți, backtest, actualizare date, chat (etapa finală)
│   │   ├── control_boti.py           pornește / oprește boții live ca procese separate
│   │   └── heatmap_oi.py             heatmap estimat al lichidărilor din Open Interest Binance
│   ├── logs/                     ← log-urile boților porniți din platformă (nu intră în git)
│   ├── data/                     ← date generate automat de pipeline (nu se editează manual)
│   │   ├── btc_live_data.csv         preț + VWAP, MACD, RSI
│   │   ├── binance_derivatives.csv   Open Interest + Funding Rate
│   │   ├── macro_mvrv_ajustat.csv    MVRV ajustat (on-chain)
│   │   ├── macro_sopr.csv            STH-SOPR (on-chain)
│   │   └── master_dataset.csv        fuziunea tuturor + Master_Index + semnal
│   │
│   ├── pipeline/                 ← colectarea și fuziunea datelor (cei 3 piloni)
│   │   ├── actualizeaza_date.py      rulează tot pipeline-ul, în ordine
│   │   ├── fetch_bgeometrics_mvrv.py Pilonul 1 – Macro (MVRV)
│   │   ├── fetch_bgeometrics_sopr.py Pilonul 1 – Macro (SOPR)
│   │   ├── fetch_binance_oi.py       Pilonul 2 – Derivate (OI, Funding)
│   │   ├── fetch_price_vwap.py       Pilonul 3 – Micro (preț, VWAP, MACD, RSI)
│   │   ├── merge_master.py           fuziune + Master_Index
│   │   ├── data_loader.py            încărcarea datasetului pentru strategii
│   │   ├── cache_util.py             cache zilnic pentru API-ul BGeometrics
│   │   └── cai.py                    căile comune ale proiectului
│   │
│   └── strategii/
│       ├── sdca/                 ← Strategia 1: Smart DCA (acumulare pe Master_Index)
│       │   ├── strategie_sdca.py     regulile de decizie (comune bot + backtest), SDCA v2
│       │   ├── backtest_sdca_long.py
│       │   ├── bot_live_hedgefound.py
│       │   └── bot_state.json        portofoliul virtual al botului
│       │
│       └── ai_hedgefund/         ← Strategia 2: AI Hedge Fund (Non-DCA, trend & momentum)
│           ├── README.md             metodologie + rezultate
│           ├── date_ai.py            istoric 2017+ și funding de la Binance
│           ├── strategie_ai.py       logica strategiei (12 voturi + filtru funding)
│           ├── backtest_ai.py
│           ├── bot_live_ai.py        simulator live
│           ├── stare_live.json       portofoliul virtual al simulatorului
│           ├── data/                 date proprii (btc_1d.csv, funding_1d.csv)
│           └── rezultate/            tranzacții backtest, echitate, jurnal live
│
├── frontend/                     ← interfața web J.A.R.V.I.S. (index.html, style.css, app.js)
└── arhiva/                       ← scripturi și date vechi, păstrate pentru istoric (nu se mai folosesc)
```

## 🖥️ Platforma J.A.R.V.I.S.

**Cel mai simplu:** dublu-click pe **`porneste_jarvis.bat`** (în folderul proiectului). Se deschide o fereastră
cu serverul și, după câteva secunde, platforma în browser. **Platforma funcționează cât timp fereastra rămâne
deschisă**; închiderea ei oprește serverul (pagina va da eroare de conexiune până la o nouă pornire).
Dacă serverul rulează deja, scriptul doar deschide pagina.

Alternativ, din terminal:
```
venv\Scripts\python.exe backend\api\server.py
```
apoi deschide **http://127.0.0.1:8000** în browser. Secțiuni:

- **COMANDĂ** – preț live, Master_Index și componentele lui, starea celor doi boți, istoricul pieței și
  comparația SDCA v2 / AI Hedge Fund / Buy & Hold pe aceeași perioadă. Consola asistentului e pregătită
  (se activează în etapa finală, cu cheia API Anthropic).
- **BOȚI LIVE** – pornește / oprește boții, rulează un ciclu la cerere, resetează portofoliul (arhivare),
  vezi log-ul live, portofoliul, semnalul curent și ultimele tranzacții. Boții rulează ca procese separate
  și continuă și după ce închizi pagina.
- **HEATMAP OI** – heatmap estimat al lichidărilor (preț × timp) construit din Open Interest-ul Binance
  Futures (15m / 1h / 4h, ~30 zile): unde s-ar declanșa lichidările long/short, nivelurile „magnet” și
  evoluția Open Interest. Model transparent în `backend/api/heatmap_oi.py` (levier presupus 10x–100x,
  împărțire long/short după taker buy/sell) — o estimare, nu date exacte.
- **BACKTEST** – alegi strategia, data de start și capitalul; primești raportul complet, graficul,
  randamentul pe ani și jurnalul cu motivul fiecărei tranzacții.

**Actualizare automată:** cât timp serverul rulează, își reîmprospătează singur datele în fundal —
pipeline-ul Master_Index la fiecare 60 de minute (BGeometrics tot o dată pe zi, prin cache) și istoricul AI
la fiecare zi nouă închisă (00:00 UTC); dacă un bot rulează, el își actualizează singur datele și serverul
nu se suprapune. Pagina verifică la 30 s dacă au apărut date noi și redesenează panourile fără reîncărcare
(indicatorul **AUTO** din bara de sus). Prețul live se actualizează la 15 s, iar heatmap-ul OI se
recalculează la 60 s. Butonul **⟳ ACTUALIZEAZĂ DATE** forțează o actualizare imediată.
Dezactivare: `$env:JARVIS_AUTO_UPDATE=0` înainte de pornirea serverului.

## 🧠 Cele două strategii

| | **SDCA** (`strategii/sdca`) | **AI Hedge Fund** (`strategii/ai_hedgefund`) |
|---|---|---|
| Tip | acumulare treptată (DCA inteligent) | Non-DCA: intră / iese în trepte de 25% |
| Semnal | Master_Index (7 indicatori Z-score, 3 piloni) | 12 voturi trend & momentum + filtru funding |
| Date | `backend/data/master_dataset.csv` (2022-07+, on-chain din 2022-11) | istoric Binance 2017+ |
| Bot live | la 3 ore, actualizează pipeline-ul | la 15 minute, preț live, decizie la închiderea zilei |

**Master_Index (SDCA)** = 0.10·(Z_VWAP + Z_MACD + Z_RSI) + 0.15·Z_Funding + 0.20·(MVRV ajustat + Z_SOPR)
→ BUY sub −0.5, SELL peste 0.8. (Open Interest e doar informativ: Binance dă ~30 zile de istoric, deci nu poate fi testat.)

### SDCA v2 (optimizare validată pe date realiste)
Backtest 2023-02-15 → 2026-11 (comisioane incluse, **date on-chain întârziate 7 zile exact ca live**), $10.000:

| | SDCA v2 | SDCA v1 | Buy & Hold |
|---|---|---|---|
| Valoare finală | **$33.557 (+236%)** | $19.110 (+91%) | $31.029 (+210%) |
| Drawdown maxim | **-28%** | -17% | -53% |
| 28 porniri lunare: medie / mediană | **+69% / +81%** | +37% / +53% | +64% / +27% |
| 28 porniri lunare: drawdown mediu | -34% | -26% | -53% |

Ce s-a schimbat (detalii în `strategie_sdca.py`):
1. **Date realiste (fără lookahead):** BGeometrics gratuit ascunde ultimele 7 zile de MVRV/SOPR. Backtest-ul
   folosea valoarea din ziua respectivă; acum o folosește abia după 7 zile, ca botul live.
2. **MVRV ajustat cu origine fixă** – benzile „alunecau” zilnic odată cu fereastra de 4 ani a API-ului.
3. **Confirmare on-chain pentru top** – vânzarea de 70% cere și MVRV în treimea de sus a benzii.
4. **Reset față de vârful real al ciclului** – v1 măsura -40% față de prețul vândut și rămânea pe cash pentru totdeauna.
5. **Fix:** alerta de euforie se șterge la un ciclu nou; **o singură logică** pentru bot și backtest; Open Interest scos din index.

Respinsă după testul pe date realiste: „ieșirea din fals top” (fără întârziere părea +205%, cu datele reale: -3% în medie).
**Limită:** datele on-chain gratuite acoperă un singur ciclu (2022-11 →), iar regulile au fost alese pe aceleași
date — rezultatele sunt indicative, nu o garanție.

## ▶️ Comenzi (din folderul proiectului, în PowerShell)

Instalare (o singură dată):
```
venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env        # apoi pune tokenul BGeometrics în .env
```
Tokenul API stă doar în `.env`, care nu intră în git (vezi `.gitignore`).

**Date (pipeline)**
```
venv\Scripts\python.exe backend\pipeline\actualizeaza_date.py
```

**Strategia SDCA**
```
venv\Scripts\python.exe backend\strategii\sdca\backtest_sdca_long.py                  # v2 vs v1 vs Buy&Hold
venv\Scripts\python.exe backend\strategii\sdca\backtest_sdca_long.py --robustete     # 29 porniri lunare
venv\Scripts\python.exe backend\strategii\sdca\bot_live_hedgefound.py                 # live, la 3 ore
venv\Scripts\python.exe backend\strategii\sdca\bot_live_hedgefound.py --offline       # o analiză, fără internet
venv\Scripts\python.exe backend\strategii\sdca\bot_live_hedgefound.py --replay 2025-01-01 --pauza 0.3
```

**Strategia AI Hedge Fund**
```
venv\Scripts\python.exe backend\strategii\ai_hedgefund\backtest_ai.py
venv\Scripts\python.exe backend\strategii\ai_hedgefund\bot_live_ai.py                 # simulator live, la 15 min
venv\Scripts\python.exe backend\strategii\ai_hedgefund\bot_live_ai.py --o-data        # un singur ciclu
```

> 💡 Dacă apar erori cu emoji-urile în consolă: `$env:PYTHONUTF8=1` înainte de rulare.

## 🌐 Surse de date
- **Binance Spot / Futures** – preț, volum, Open Interest, Funding Rate (API public, fără cheie)
- **BGeometrics** – MVRV, STH-SOPR (token API; descărcat cel mult o dată pe zi). Plan gratuit: ultimii 4 ani,
  10 cereri/oră, ultimele 7 zile ascunse. Istoricul descărcat se păstrează local și nu se mai pierde.

## ⚠️ Notă
Toate tranzacțiile sunt **simulate** – niciun bot nu trimite ordine reale. Rezultatele din backtest
nu garantează rezultate viitoare. Proiect academic, nu recomandare de investiții.
