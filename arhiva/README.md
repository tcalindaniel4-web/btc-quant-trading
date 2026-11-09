# 🗄️ Arhivă

Scripturi și date din primele versiuni ale proiectului, păstrate pentru istoric (evoluția codului).
**Nu mai sunt folosite** de pipeline sau de strategii și nu sunt adaptate la noua structură de foldere.

| Fișier | Ce era | Înlocuit de |
|---|---|---|
| `live_updater.py` | actualizare preț + VWAP la 6 ore | `backend/pipeline/fetch_price_vwap.py` |
| `price_action.py` | suport/rezistență, ATR, impulsuri (fost conținut al `merge_master.py`) | – (neutilizat) |
| `data/btc_istoric.csv` | primul istoric descărcat (1000 zile) | `backend/data/btc_live_data.csv` |
| `data/btc_cu_indicatori.csv` | istoric + RSI (sursa bug-ului cu date înghețate) | `backend/data/master_dataset.csv` |
| `data/mvrv.json` | export MVRV brut | `backend/data/macro_mvrv_ajustat.csv` |
