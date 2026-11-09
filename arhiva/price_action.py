import pandas as pd
import numpy as np

def calculeaza_price_action(df):
    """
    Adaugă indicatori de Price Action pe DataFrame-ul existent.
    Necesită coloanele: 'Open', 'High', 'Low', 'Close', 'Volume'
    (Mutat din merge_master.py, care acum face din nou fuziunea datelor.)
    """

    # 1. SUPORT ȘI REZISTENȚĂ (Fereastră de 20 de zile)
    # Rezistența: cel mai mare preț atins în ultimele 20 de zile
    df['Rezistenta_20d'] = df['High'].rolling(window=20).max()
    # Suport: cel mai mic preț atins în ultimele 20 de zile
    df['Suport_20d'] = df['Low'].rolling(window=20).min()

    # Calculăm distanța prețului curent față de Suport/Rezistență (în procente)
    df['Distanta_Suport_%'] = ((df['Close'] - df['Suport_20d']) / df['Suport_20d']) * 100

    # 2. ATR (Average True Range) - Măsoară volatilitatea pură
    df['H-L'] = df['High'] - df['Low']
    df['H-PC'] = abs(df['High'] - df['Close'].shift(1))
    df['L-PC'] = abs(df['Low'] - df['Close'].shift(1))
    df['TR'] = df[['H-L', 'H-PC', 'L-PC']].max(axis=1)
    df['ATR_14'] = df['TR'].rolling(window=14).mean()

    # 3. MIȘCĂRI IMPULSIVE (Breakouts)
    # Definiție: Lumânare verde a cărei corp este de 1.5x mai mare decât volatilitatea medie (ATR)
    # și volumul este peste media ultimelor 20 de zile.
    df['Corp_Lumanare'] = abs(df['Close'] - df['Open'])
    df['Volum_Mediu_20d'] = df['Volume'].rolling(window=20).mean()

    # Creăm semnale booleene (True/False)
    df['Impuls_Ascendent'] = (
        (df['Close'] > df['Open']) &
        (df['Corp_Lumanare'] > 1.5 * df['ATR_14']) &
        (df['Volume'] > df['Volum_Mediu_20d'])
    )

    df['Impuls_Descendent'] = (
        (df['Close'] < df['Open']) &
        (df['Corp_Lumanare'] > 1.5 * df['ATR_14']) &
        (df['Volume'] > df['Volum_Mediu_20d'])
    )

    # Curățăm coloanele temporare de calcul pentru a păstra DataFrame-ul curat
    df.drop(columns=['H-L', 'H-PC', 'L-PC', 'TR', 'Corp_Lumanare'], inplace=True)

    return df
