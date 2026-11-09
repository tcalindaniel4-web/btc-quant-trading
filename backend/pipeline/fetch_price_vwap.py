import sys
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from cai import DATA_DIR

print("Preluăm datele de preț și calculăm VWAP, MACD și RSI de la Binance Spot...")

# Istoric de la 2022-06: acoperă datele on-chain disponibile gratuit (din 2022-11) + încălzirea indicatorilor.
START = '2022-06-01'


def descarca_lumanari():
    """Lumânări zilnice BTCUSDT de la START până azi (paginat: Binance dă max 1000 / cerere). Date în UTC."""
    url = "https://api.binance.com/api/v3/klines"
    start_ms = int(pd.Timestamp(START, tz='UTC').timestamp() * 1000)
    toate = []
    while True:
        response = requests.get(url, params={"symbol": "BTCUSDT", "interval": "1d", "startTime": start_ms, "limit": 1000},
                                timeout=30)
        if response.status_code != 200:
            return None, response.status_code
        data = response.json()
        toate.extend(data)
        if len(data) < 1000:
            return toate, 200
        start_ms = data[-1][0] + 1


def fetch_and_process_micro():
    try:
        data, status = descarca_lumanari()

        if data:
            rezultate = []

            for candle in data:
                data_calendaristica = datetime.fromtimestamp(candle[0] / 1000, tz=timezone.utc).strftime('%Y-%m-%d')
                open_ = float(candle[1])
                high = float(candle[2])
                low = float(candle[3])
                close = float(candle[4])
                volume = float(candle[5])
                rezultate.append([data_calendaristica, open_, high, low, close, volume])

            df = pd.DataFrame(rezultate, columns=['Data', 'Open', 'High', 'Low', 'Close', 'Volume'])
            fereastra_z = 30
            
            # --- 1. CALCUL VWAP ---
            df['Typical_Price'] = (df['High'] + df['Low'] + df['Close']) / 3
            df['TP_x_Volume'] = df['Typical_Price'] * df['Volume']
            fereastra_vwap = 14
            df['Cum_TP_x_Vol'] = df['TP_x_Volume'].rolling(window=fereastra_vwap).sum()
            df['Cum_Vol'] = df['Volume'].rolling(window=fereastra_vwap).sum()
            df['VWAP'] = df['Cum_TP_x_Vol'] / df['Cum_Vol']
            
            df['Deviatie_VWAP'] = df['Close'] - df['VWAP']
            df['Dev_Mean'] = df['Deviatie_VWAP'].rolling(window=fereastra_z).mean()
            df['Dev_Std'] = df['Deviatie_VWAP'].rolling(window=fereastra_z).std()
            df['Z_VWAP'] = (df['Deviatie_VWAP'] - df['Dev_Mean']) / df['Dev_Std']
            
            # --- 2. CALCUL MACD (12, 26, 9) ---
            df['EMA_12'] = df['Close'].ewm(span=12, adjust=False).mean()
            df['EMA_26'] = df['Close'].ewm(span=26, adjust=False).mean()
            df['MACD_Line'] = df['EMA_12'] - df['EMA_26']
            df['Signal_Line'] = df['MACD_Line'].ewm(span=9, adjust=False).mean()
            df['MACD_Histogram'] = df['MACD_Line'] - df['Signal_Line']
            
            df['MACD_Mean'] = df['MACD_Histogram'].rolling(window=fereastra_z).mean()
            df['MACD_Std'] = df['MACD_Histogram'].rolling(window=fereastra_z).std()
            df['Z_MACD'] = (df['MACD_Histogram'] - df['MACD_Mean']) / df['MACD_Std']
            
            # --- 3. CALCUL RSI (14 zile) ---
            delta = df['Close'].diff()
            gain = delta.where(delta > 0, 0.0)
            loss = -delta.where(delta < 0, 0.0)
            
            avg_gain = gain.ewm(alpha=1/14, adjust=False).mean()
            avg_loss = loss.ewm(alpha=1/14, adjust=False).mean()
            
            rs = avg_gain / avg_loss
            df['RSI'] = 100 - (100 / (1 + rs))
            
            df['RSI_Mean'] = df['RSI'].rolling(window=fereastra_z).mean()
            df['RSI_Std'] = df['RSI'].rolling(window=fereastra_z).std()
            df['Z_RSI'] = (df['RSI'] - df['RSI_Mean']) / df['RSI_Std']
            
            # Curățăm datele și salvăm
            # Păstrăm și OHLCV, ca master_dataset.csv să fie singura sursă de date pentru boți.
            df_final = df[['Data', 'Open', 'High', 'Low', 'Close', 'Volume',
                           'VWAP', 'Z_VWAP', 'MACD_Histogram', 'Z_MACD', 'RSI', 'Z_RSI']].dropna()
            df_final.to_csv(DATA_DIR / 'btc_live_data.csv', index=False)
            
            print(f"✅ Succes! Datele micro/execuție salvate (Zile analizate: {len(df_final)}).")
            print(f"Ultimul Preț BTC: {df_final.iloc[-1]['Close']:.2f}$")
            print(f"Ultimul Z-Score (VWAP): {df_final.iloc[-1]['Z_VWAP']:.3f}")
            print(f"Ultimul Z-Score (MACD): {df_final.iloc[-1]['Z_MACD']:.3f}")
            print(f"Ultimul Z-Score (RSI): {df_final.iloc[-1]['Z_RSI']:.3f} (RSI brut: {df_final.iloc[-1]['RSI']:.0f})")
            
        else:
            print(f"❌ Eroare Binance Spot API: {status}")
            sys.exit(1)

    except Exception as e:
        print(f"❌ A apărut o eroare: {e}")
        sys.exit(1)

if __name__ == "__main__":
    fetch_and_process_micro()