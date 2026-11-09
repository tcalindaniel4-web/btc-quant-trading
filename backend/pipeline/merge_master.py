import sys
import pandas as pd
from cai import DATA_DIR

# =============================================================================
# FUZIUNE & DECIZIE (MASTER)
# Unește cei 3 piloni într-un singur fișier: data/master_dataset.csv
#   - Micro (bază, zilnic):  data/btc_live_data.csv       (OHLCV + VWAP/MACD/RSI)
#   - Derivate:              data/binance_derivatives.csv (Z OI, Z Funding)
#   - Macro (on-chain):      data/macro_mvrv_ajustat.csv, data/macro_sopr.csv
#
# Ponderi Master_Index (reconstruite exact din master_dataset.csv-ul anterior):
#   Micro 30%  (VWAP, MACD, RSI      - câte 0.10)
#   Derivate 15% (Funding 0.15; Open Interest 0 - vezi mai jos)
#   Macro 40%  (Adjusted MVRV, SOPR  - câte 0.20)
#
# SDCA v2: Open Interest NU mai intră în index. Binance dă doar ~30 de zile de istoric OI,
# deci în backtest a fost mereu 0, iar live adăuga până la ±0.3 la index -> strategia live
# nu era strategia testată. Coloana rămâne în dataset ca informație.
# =============================================================================

PONDERI = {
    'Z_VWAP': 0.10,
    'Z_MACD': 0.10,
    'Z_RSI': 0.10,
    'Z_Open_Interest': 0.0,
    'Z_Funding_Rate': 0.15,
    'Adjusted_MVRV': 0.20,
    'Z_SOPR': 0.20,
}
PRAG_BUY = -0.5
PRAG_SELL = 0.8

# Întârzierea datelor on-chain (zile): planul gratuit BGeometrics ascunde ultimele 7 zile de MVRV/SOPR.
# Valoarea zilei D devine cunoscută abia în ziua D+7, așa că în dataset o atașăm zilei D+7.
# Fără asta, backtest-ul "vedea" MVRV/SOPR cu 7 zile înainte să fie publicate (lookahead bias),
# în timp ce botul live folosea oricum valoarea veche de 7 zile. Cu abonament plătit -> 0 sau 1.
INTARZIERE_ONCHAIN_ZILE = 7

COLOANE_MICRO = ['Data', 'Open', 'High', 'Low', 'Close', 'Volume',
                 'VWAP', 'Z_VWAP', 'MACD_Histogram', 'Z_MACD', 'RSI', 'Z_RSI']


def citeste(cale, coloane):
    df = pd.read_csv(cale)
    lipsa = [c for c in coloane if c not in df.columns]
    if lipsa:
        raise ValueError(f"{cale.name} nu are coloanele {lipsa}. Rulează din nou scriptul care îl generează.")
    df = df[coloane].copy()
    df['Data'] = pd.to_datetime(df['Data']).dt.strftime('%Y-%m-%d')
    return df.drop_duplicates(subset='Data', keep='last')


def semnal(index):
    if index < PRAG_BUY:
        return 'BUY'
    if index > PRAG_SELL:
        return 'SELL'
    return 'HOLD'


def construieste_master():
    micro = citeste(DATA_DIR / 'btc_live_data.csv', COLOANE_MICRO)
    deriv = citeste(DATA_DIR / 'binance_derivatives.csv', ['Data', 'Z_Open_Interest', 'Z_Funding_Rate'])
    mvrv = citeste(DATA_DIR / 'macro_mvrv_ajustat.csv', ['Data', 'Adjusted_MVRV'])
    sopr = citeste(DATA_DIR / 'macro_sopr.csv', ['Data', 'Z_SOPR'])

    # Avertizăm dacă un pilon are date prea vechi față de preț (ex. API-ul a picat zile la rând).
    ultima_zi_pret = pd.to_datetime(micro['Data'].max())
    for nume, extra, toleranta in (('Derivate', deriv, 3), ('MVRV', mvrv, 10), ('SOPR', sopr, 10)):
        intarziere = (ultima_zi_pret - pd.to_datetime(extra['Data'].max())).days
        if intarziere > toleranta:
            print(f"⚠️ {nume}: ultimele date sunt din {extra['Data'].max()} ({intarziere} zile în urma prețului).")

    # Fiecare valoare on-chain e atașată zilei în care devine disponibilă (D + întârziere).
    def disponibil_de_la(extra):
        extra = extra.copy()
        extra['Data_OnChain'] = extra['Data']
        extra['Data'] = (pd.to_datetime(extra['Data']) + pd.Timedelta(days=INTARZIERE_ONCHAIN_ZILE)).dt.strftime('%Y-%m-%d')
        return extra

    mvrv = disponibil_de_la(mvrv)
    sopr = disponibil_de_la(sopr).drop(columns='Data_OnChain')

    df = micro.sort_values('Data').reset_index(drop=True)
    for extra in (deriv, mvrv, sopr):
        df = df.merge(extra, on='Data', how='left')

    # Dacă datele întârzie mai mult decât de obicei -> propagăm ultima valoare cunoscută.
    df[['Adjusted_MVRV', 'Z_SOPR', 'Data_OnChain']] = df[['Adjusted_MVRV', 'Z_SOPR', 'Data_OnChain']].ffill()
    # Istoric fără date (ex. OI/Funding înainte de fereastra Binance) -> neutru (0).
    df[list(PONDERI)] = df[list(PONDERI)].fillna(0.0)

    df['Master_Index'] = sum(df[col] * w for col, w in PONDERI.items())
    df['Semnal'] = df['Master_Index'].apply(semnal)

    df.to_csv(DATA_DIR / 'master_dataset.csv', index=False)

    ultim = df.iloc[-1]
    print(f"✅ Master dataset generat: {len(df)} zile ({df.iloc[0]['Data']} -> {ultim['Data']}).")
    print(f"Ultimul Master_Index: {ultim['Master_Index']:+.3f} | Semnal: {ultim['Semnal']} | Preț: {ultim['Close']:,.2f}$")
    print(f"Date on-chain folosite: din {ultim['Data_OnChain']} (întârziere {INTARZIERE_ONCHAIN_ZILE} zile, ca live)")


if __name__ == "__main__":
    try:
        construieste_master()
    except Exception as e:
        print(f"❌ Eroare la fuziune: {e}", file=sys.stderr)
        sys.exit(1)  # cod != 0 ca actualizeaza_date.py să oprească pipeline-ul
