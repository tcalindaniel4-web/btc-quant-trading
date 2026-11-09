# 🤖 AI Hedge Fund – strategie Non-DCA (separată de strategia SDCA)

**Ansamblu Trend & Momentum cu filtru de Funding** – long BTC / cash, fără levier, fără DCA.

## Cum decide
12 „experți” votează zilnic dacă BTC e pe trend ascendent:
- **Trend (6):** `Close > SMA(n)`, n = 20, 40, 80, 120, 160, 200 zile
- **Momentum (6):** randament pe n zile > 0, n = 14, 30, 60, 90, 180, 365 zile

Procentul de voturi „DA” = cât din capital stă în BTC (trepte de 25%, schimbare doar dacă ținta se mută cu >15pp).
**Filtru funding:** dacă funding-ul mediu pe 7 zile > 0.05%/8h (long-uri supra-îndatorate) → expunerea se înjumătățește.

## Metodologie
- Date Binance zilnice 2017 → azi (3 cicluri bull/bear), funding din 2019.
- Strategia aleasă pe **2018–2022 (train)**, validată o singură dată pe **2023–2026 (test)**.
- Comision 0.10% + slippage 0.05% la fiecare tranzacție; semnal pe zi închisă (fără lookahead).
- Respinse (nu au rezistat pe test sau au stricat rezultatele): Donchian 55/20, SMA200, EMA50/200,
  volatility targeting, crash-guard ATR, dip-buy RSI, poziție „convexă” (supra-ajustare pe train).

## Rezultate ($10.000)
| Perioadă | AI CAGR | AI Max DD | B&H CAGR | B&H Max DD |
|---|---|---|---|---|
| 2018-08 → 2026-11 | **45.7%** ($221.7k) | **-47%** | 34.3% ($113.7k) | -77% |
| Test 2023 → 2026 | 41.4% | **-27%** | 47.7% | -53% |

Câștigă mult în bear market (2018: -13% vs -44%; 2022: -28% vs -65%), rămâne în urmă în bull run-uri puternice
(2023–2024), pentru că intră treptat. Avantajul principal: același randament sau mai mare, cu jumătate din risc.

## Comenzi (din folderul proiectului)
```
venv\Scripts\python.exe backend\strategii\ai_hedgefund\date_ai.py                     # descarcă/actualizează datele
venv\Scripts\python.exe backend\strategii\ai_hedgefund\backtest_ai.py                 # backtest 2018 -> azi
venv\Scripts\python.exe backend\strategii\ai_hedgefund\backtest_ai.py --start 2023-01-01
venv\Scripts\python.exe backend\strategii\ai_hedgefund\bot_live_ai.py --capital 10000 # simulator live (Ctrl+C oprește)
venv\Scripts\python.exe backend\strategii\ai_hedgefund\bot_live_ai.py --o-data        # un singur ciclu
venv\Scripts\python.exe backend\strategii\ai_hedgefund\bot_live_ai.py --reset         # portofoliu virtual nou
```
Simulatorul e **paper trading**: nu trimite ordine reale. Starea: `stare_live.json`, tranzacții: `rezultate/jurnal_live.csv`.

⚠️ Rezultatele trecute nu garantează rezultate viitoare. Proiect academic, nu recomandare de investiții.
