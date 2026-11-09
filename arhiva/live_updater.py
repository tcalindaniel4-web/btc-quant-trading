import pandas as pd
import numpy as np
import requests
from datetime import datetime
import os
import schedule
import time

# --- 1. SETĂRI ---
symbol = "BTCUSDT"
interval = "1d"
limit = 2 # Tragem doar ultimele 2 zile pentru a nu suprasolicita API-ul
url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
fisier_date = 'data/btc_live_data.csv'

def actualizeaza_datele_si_indicatorii():
    ora_curenta = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"\n[{ora_curenta}] Începem actualizarea datelor...")

    # --- 2. PRELUAREA DATELOR NOI (Binance) ---
    try:
        response = requests.get(url)
        data = response.json()
        date_noi = []
        for row in data:
            timestamp = datetime.fromtimestamp(row[0] / 1000).strftime('%Y-%m-%d')
            date_noi.append([timestamp, float(row[1]), float(row[2]), float(row[3]), float(row[4]), float(row[5])])
        
        df_nou = pd.DataFrame(date_noi, columns=['Data', 'Open', 'High', 'Low', 'Close', 'Volume'])
    except Exception as e:
        print(f"[{ora_curenta}] Eroare la preluarea datelor: {e}")
        return # Ieșim din funcție, dar botul rămâne activ pentru următoarea încercare

    # --- 3. ACTUALIZAREA FIȘIERULUI ISTORIC ---
    if os.path.exists(fisier_date):
        df_istoric = pd.read_csv(fisier_date)
        # Eliminăm zilele care se suprapun (pentru a le actualiza cu datele cele mai recente)
        df_istoric = df_istoric[~df_istoric['Data'].isin(df_nou['Data'])]
        df_final = pd.concat([df_istoric, df_nou], ignore_index=True)
    else:
        print(f"[{ora_curenta}] Fișierul {fisier_date} nu există. Se va crea unul nou (dar atenție, va conține doar 2 zile!).")
        df_final = df_nou

    # Sortăm cronologic
    df_final = df_final.sort_values(by='Data').reset_index(drop=True)

    # --- 4. CALCULUL INDICATORILOR (VWAP & Z-Scores) ---
    df_final['Typical_Price'] = (df_final['High'] + df_final['Low'] + df_final['Close']) / 3
    df_final['Volume_x_TypicalPrice'] = df_final['Typical_Price'] * df_final['Volume']
    df_final['Rolling_VWAP'] = df_final['Volume_x_TypicalPrice'].rolling(window=14).sum() / df_final['Volume'].rolling(window=14).sum()

    rolling_mean_vwap = df_final['Rolling_VWAP'].rolling(window=90).mean()
    rolling_std_vwap = df_final['Rolling_VWAP'].rolling(window=90).std()
    df_final['Z_VWAP'] = (df_final['Rolling_VWAP'] - rolling_mean_vwap) / rolling_std_vwap

    df_final = df_final.drop(columns=['Typical_Price', 'Volume_x_TypicalPrice'])
    
    # Salvăm fișierul
    df_final.to_csv(fisier_date, index=False)

    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Actualizare completă. Ultimul preț: {df_final.iloc[-1]['Close']}$")
    print(f"Ultimul Z-Score (VWAP): {df_final.iloc[-1]['Z_VWAP']:.3f}")

# --- 5. LOGICA DE SCHEDULING (BUCLA INFINITĂ) ---

# Instalarea pachetului necesar: pip install schedule (dacă nu l-ai instalat deja)
print("Pornim Bot-ul de actualizare. Apasă Ctrl+C pentru a opri.")

# Programăm execuția (aici, pentru testare, poți pune ".minutes", dar pentru producție pui ".hours")
# schedule.every(1).minutes.do(actualizeaza_datele_si_indicatorii) # Folosește linia asta DOAR pentru un test rapid de 1 minut
schedule.every(6).hours.do(actualizeaza_datele_si_indicatorii) 

# Executăm funcția o dată chiar acum, la pornire, ca să nu așteptăm 6 ore prima dată
actualizeaza_datele_si_indicatorii()

while True:
    schedule.run_pending()
    time.sleep(60) # Verifică ceasul intern la fiecare minut