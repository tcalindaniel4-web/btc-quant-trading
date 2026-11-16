# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Bachelor-thesis project: a simulated (paper-trading) BTC quant system with two independent strategies (SDCA and AI Hedge Fund), each with a backtest and a live bot, plus a FastAPI + vanilla-JS web platform ("VEGA"). Code, identifiers, comments, logs and UI text are in **Romanian**. Keep new code and user-facing text in Romanian, and reply to the user in Romanian. No bot ever places real orders.

## Commands (PowerShell, from repo root, Windows venv)

```
venv\Scripts\python.exe -m pip install -r requirements.txt
venv\Scripts\python.exe backend\api\server.py [--deschide]       # platform at http://127.0.0.1:8000 (or double-click porneste_jarvis.bat)
venv\Scripts\python.exe backend\pipeline\actualizeaza_date.py    # rebuild backend/data/*.csv + master_dataset.csv
venv\Scripts\python.exe backend\strategii\sdca\backtest_sdca_long.py [--start YYYY-MM-DD --capital N --v1 --robustete]
venv\Scripts\python.exe backend\strategii\sdca\bot_live_hedgefound.py [--offline | --replay YYYY-MM-DD --pauza 0.3 | --o-data]
venv\Scripts\python.exe backend\strategii\ai_hedgefund\backtest_ai.py [--start --end --capital]
venv\Scripts\python.exe backend\strategii\ai_hedgefund\bot_live_ai.py [--o-data | --offline | --reset]
```

- Set `$env:PYTHONUTF8=1` if the console chokes on emoji. `$env:JARVIS_AUTO_UPDATE=0` disables the server's background data refresh.
- There is no test suite or linter. Verify strategy changes with `backtest_sdca_long.py --robustete` (multi-start robustness) and `backtest_ai.py`; verify UI changes in the running server.
- Secrets: `BGEOMETRICS_TOKEN` lives only in `.env` (see `.env.example`), loaded by `backend/pipeline/cai.py`.

## Architecture

**Not a Python package.** Modules import each other as flat scripts: `server.py` and `backtest_sdca_long.py` push `backend/pipeline`, `backend/strategii/sdca`, `backend/strategii/ai_hedgefund` and `backend/api` onto `sys.path`, then `import strategie_sdca`, `data_loader`, etc. Module names must stay unique across those folders. All paths come from `cai.py`.

**Data pipeline (`backend/pipeline`)** → `backend/data/*.csv` (generated, gitignored). Three "pillars" are fetched separately (BGeometrics MVRV/SOPR on-chain, Binance OI/funding, Binance price + VWAP/MACD/RSI), then `merge_master.py` computes `Master_Index` with the weights in `PONDERI`:
`0.10·(Z_VWAP+Z_MACD+Z_RSI) + 0.15·Z_Funding + 0.20·(Adjusted_MVRV+Z_SOPR)`; OI weight is 0 (Binance only gives ~30 days).
- On-chain values are deliberately lagged by `INTARZIERE_ONCHAIN_ZILE = 7` days, because the free BGeometrics tier hides the last 7 days. Backtests must use the same lag as live, so never remove it (it removed a lookahead bias that had inflated earlier results).
- BGeometrics is limited to 10 requests per hour, 4 years of history and at most one download per day (`cache_util.e_descarcat_azi`). Downloaded history is kept locally and merged, never overwritten. Adjusted-MVRV bands use a fixed origin (`ORIGINE_BENZI`).

**SDCA strategy (`backend/strategii/sdca`)**: `strategie_sdca.decide(state, azi, v2=True)` is the **single decision function shared by the live bot and the backtest**. Change rules there only, never in the bot or backtest separately. Its docstring records the rules (MVRV-confirmed top sale of 70% + moonbag, reset at -40% from the cycle peak, buyback ≥10% below the sale price) and the variants that were tested and rejected. `backtest_sdca_long.simuleaza(df, start, end, capital, v2)` returns equity, a trade journal with a reason per trade (`De_ce`), events, fees and the final state. SDCA data starts in 2022-07, and full on-chain data in 2022-11.

**AI Hedge Fund (`backend/strategii/ai_hedgefund`)**: has its own data (`date_ai.py`, Binance 2017+ in its own `data/`). `strategie_ai.py` combines 12 trend/momentum votes with a funding filter and moves exposure in 25% steps with hysteresis. `backtest_ai.ruleaza_backtest(ind, start, end, capital)`. Methodology is in its `README.md`.

**Live bots** keep their portfolio in JSON state files (`sdca/bot_state.json`, `ai_hedgefund/stare_live.json`, gitignored). The server starts and stops them as separate processes via `backend/api/control_boti.py`, with PID files and logs in `backend/logs/`, so they outlive the web page.

**Server (`backend/api/server.py`)**: FastAPI serves `frontend/` as static files plus `/api/*` (market, bots, backtests, heatmap, news, status, update). A background thread (`_bucla_auto`) reruns the pipeline when `master_dataset.csv` is older than 60 minutes and the AI data once per closed day, and skips this while a bot is running. `heatmap_oi.py` estimates a liquidation heatmap from Binance OI with an assumed leverage mix. `stiri.py` aggregates public RSS feeds and Yahoo quotes. `/api/chat` is a placeholder returning 503 until an Anthropic API key is added (planned final stage).

**Frontend (`frontend/`)**: one-page vanilla JS (`app.js`) using Chart.js with the zoom plugin (CDN), a Binance WebSocket for the live price, polling `/api/status` every 30 s, and tabs COMANDĂ / BOȚI LIVE / HEATMAP OI / ȘTIRI / BACKTEST. It is also a PWA (manifest + icons) reached from a phone via Tailscale. Keep it tailnet-only (no public Funnel), since the API can control the bots.

`arhiva/` is old code kept for history; don't use or edit it.

## Conventions and pitfalls

- **Never rewrite files with PowerShell `Get-Content`/`Set-Content`**: it double-encodes UTF-8 and corrupts the Romanian diacritics and emoji used throughout. Use the Edit/Write tools.
- Strategy changes need validation on many start dates, not one backtest: the monthly starts over the current cycle (`--robustete`), comparing mean, median, worst case and drawdown against the current rules. Rules were tuned on a single cycle of on-chain data, so treat single-scenario improvements with suspicion.
- Fees are modelled as 0.10% + 0.05% slippage (0.15%).
- The repo is public on GitHub: never commit `.env`, generated data, bot state or logs (all covered by `.gitignore`).
