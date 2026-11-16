"""
STRATEGIA SDCA (Smart DCA pe Master_Index) - logica de decizie, folosită IDENTIC de:
  - bot_live_hedgefound.py (live / offline / replay)
  - backtest_sdca_long.py

Înainte, backtest-ul și botul aveau două copii diferite ale regulilor, deci botul live nu era
strategia testată. Acum există o singură sursă.

SDCA v2 = regulile originale + 3 corecții:
  1. CONFIRMARE ON-CHAIN PENTRU TOP: "alerta roșie" (care armează vânzarea de 70%) cere și MVRV
     ajustat în treimea de sus a benzii de evaluare (>= (2/3)^1.5 ≈ 0.544). Fără ea, botul vindea
     la vârfuri locale (ex. ian. 2024 la $42.7k, cu MVRV abia la mijlocul benzii).
  2. RESET FAȚĂ DE VÂRFUL REAL: reacumularea începe la -40% de la cel mai mare preț al ciclului,
     nu de la prețul la care am vândut (altfel botul rămânea pe cash pentru totdeauna dacă piața
     urca mai sus după vânzare - exact ce s-a întâmplat în 2024-2026).
  3. FIX: la începutul unui ciclu nou, alerta de euforie din ciclul trecut se șterge.
  4. RĂSCUMPĂRARE LA REDUCERE: un semnal de top nu poate ști dacă e vârful ciclului sau doar un vârf
     local (martie 2024, $65k: cea mai mare supraevaluare MVRV a ciclului, dar prețul a ajuns ulterior
     la $126k). În loc să ghicim, după vânzare cumpărăm înapoi dacă piața capitulează (Master_Index < -0.5)
     la un preț cu ≥10% sub cel de vânzare: mai mult BTC decât înainte, din aceiași bani.
     Rezultat identic pentru orice prag între 5% și 15% (nu depinde de o valoare anume); în bear market-ul
     2021-2022 (test separat, cu MVRV istoric CoinMetrics) nu a înrăutățit rezultatul.
  5. EUFORIE LA ATH NOU (A1): alerta de top se armează de la Master_Index ≥ +1.0 (în loc de +1.5) DOAR
     dacă BTC a făcut un ATH nou în ultimele 90 de zile; altfel pragul rămâne +1.5. Euforia reală apare în
     teritoriu de preț nou; un Z mare sub vechiul ATH e doar o revenire (nov. 2020, $17k: Z ≥ 1 fără ATH
     nou - pragul de 1.0 fără condiție vindea acolo). Test 2026-11, 56 de porniri: mai bun în 30, mai slab
     în 0; ciclul curent mediană +90% → +107%, cel mai slab caz -31% → -10%, drawdown maxim -53% → -36%;
     2018 → azi medie +513% → +640% (Master_Index reconstruit aproximativ înainte de 2022-11).
     Condiția de ATH a fost aleasă după ce am văzut eșecul din 2020, deci există risc de potrivire pe istorie.
     ATH-ul se calculează din istoricul complet de preț (btc_1d.csv, din 2017), nu din master_dataset (2022-07+).
  6. CUMPĂRARE RAPIDĂ LA CAPITULARE: sub Master_Index -0.5 se cumpără tot la 7 zile, dar în orice zi din pauză
     în care Master_Index e sub -0.8 se cumpără în ziua respectivă (cel mult o dată pe zi). Înlocuiește vechea
     excepție „preț cu ≥10% sub ultima cumpărare”. Motiv: în nov. 2026 un micro-buy la Z -0.05 a pornit pauza
     de 7 zile, iar prima intrare mare (70%) a fost blocată deși Z ajunsese la -0.94. Test 2026-11-13, 56 de
     porniri: ciclul curent medie +90% → +97%, mai bun în 15 / mai slab în 13; 2018 → azi medie +617% → +644%,
     mediană +252% → +278%, mai bun în 18 / mai slab în 10; drawdown neschimbat. Varianta „doar în ziua în care
     Z trece sub -0.8” (o singură dată) era mai slabă în 17/28 și 24/28 porniri; pragul -1.0 era mai slab în 27/28.

Validare pe date REALISTE (MVRV/SOPR întârziate 7 zile, cum le vede botul live), 28 de porniri
lunare 2023-03 .. 2025-06: vezi `backtest_sdca_long.py --robustete` (cifrele se schimbă odată cu piața).
La adăugarea regulii 4: medie +88% față de +64% fără ea, mediană +86% față de +75%, același drawdown,
rezultat mai bun în 21 din 28 de porniri și egal în rest.
Limită: date on-chain complete doar din 2022-11 => un singur ciclu; regulile au fost alese după ce am
văzut aceste date, deci dovada e mai slabă decât un test pe date complet noi. Câștigul regulii 4 vine
în principal dintr-un singur episod (corecția din august-septembrie 2024).

Testat și RESPINS (pe date realiste):
  - VÂNZARE ÎN TRANȘE MAI MICI (33% / 50% / proporțional cu MVRV) cu păstrarea restului: mai slab decât
    70% + moonbag (medie +49..54% față de +64%), pentru că restul era ținut prin scăderea din 2025-2026.
  - TRAILING STOP sau „următorul semnal de vârf” în loc de +20% fix pentru moonbag: media crește, dar
    mediana scade și câștigă doar în 13/28 porniri (un singur episod) - dovadă insuficientă.
  - IEȘIRE DIN "FALS TOP" (reluarea acumulării când prețul depășește vârful vândut): fără
    întârzierea on-chain părea foarte bună (+205%), dar cu datele reale reintra târziu în ciclu
    ($113k în 2025) și ținea poziția prin prăbușire: medie -3%, drawdown -50%. Codul rămâne,
    dezactivat prin IESIRE_FALS_TOP = False.
  - Reintrare agresivă imediată la breakout (cumpăra exact la vârfuri).
  - MICRO-SELL 5-10% la Master_Index 0.8..1: vinde la începutul bull run-ului (ian.-feb. 2024, $45-52k);
    mai slab în 17-20 din 28 de porniri. MICRO-BUY doar până la -0.4 (în loc de 0): neutru (15 / 13).
Rezultate: vezi backtest_sdca_long.py.
"""
from pathlib import Path

import pandas as pd

PRAG_MVRV_TOP = (2 / 3) ** 1.5   # MVRV în treimea de sus a benzii (scara MVRV ajustat ridicată la 1.5)
PRAG_Z_EUFORIE = 1.5
# Cumpărare rapidă în pauza de 7 zile (regula 6): dacă Master_Index scade sub REINTRARE_Z, cumpărăm în ziua
# respectivă fără să așteptăm 7 zile. Mod 'traversare' = doar în ziua în care Z trece sub prag (o dată pe
# traversare); 'zilnic' = în fiecare zi cu Z sub prag (cel mult o dată pe zi); None = dezactivat.
# REINTRARE_PASTREAZA_10: păstrează și vechea condiție (preț cu ≥10% sub ultima cumpărare).
REINTRARE_Z = -0.8
REINTRARE_MOD = 'zilnic'
REINTRARE_PASTREAZA_10 = False
PRAG_Z_EUFORIE_ATH = 1.0        # pragul de euforie când BTC a făcut un ATH nou în ultimele 90 de zile (regula 5)
FEREASTRA_ATH = 90
# istoricul complet de preț (din 2017); master_dataset.csv începe abia în 2022-07, deci nu știe ATH-ul din 2021
ISTORIC_PRET = Path(__file__).resolve().parent.parent / 'ai_hedgefund' / 'data' / 'btc_1d.csv'
# rezervă dacă fișierul lipsește: ATH-ul Binance din 2021-11-10
ATH_REZERVA = ('2021-11-10', 69000.0)
IESIRE_FALS_TOP = False          # respinsă în validarea pe date realiste (vezi mai sus)
RASCUMPARARE_REDUCERE = 0.10     # răscumpărare după vânzare: preț cu ≥10% sub vânzare + capitulare (0 = dezactivat)


def stare_noua(capital):
    return {
        "capital_initial": capital, "cash": capital, "btc": 0.0,
        "total_investit": 0.0, "zile_de_la_buy": 999, "ultimul_pret_buy": 0.0,
        "nivel_suport_curent": 0.0, "profit_lock_activ": False, "prima_intrare_facuta": False,
        "interdictie_macro_activa": False, "ultimul_peak_cunoscut": 0.0, "macro_top_trecut": 0.0,
        "alerta_rosie_euforie": False, "distributie_finala_activa": False, "pret_vanzare_70": 0.0,
        "ultima_rulare": "N/A"
    }


def zile_intre(data_veche, data_noua):
    """Câte zile calendaristice au trecut între două date 'YYYY-MM-DD' (0 dacă data veche lipsește)."""
    try:
        return max(0, (pd.to_datetime(data_noua) - pd.to_datetime(data_veche)).days)
    except (ValueError, TypeError):
        return 0


def _ath_istoric(date):
    """ATH-ul (cel mai mare High) atins până la fiecare zi din `date`, din istoricul complet de preț."""
    try:
        px = pd.read_csv(ISTORIC_PRET, usecols=['Data', 'High']).sort_values('Data')
        ath = px.set_index('Data')['High'].cummax()
        return ath.reindex(ath.index.union(date)).ffill().reindex(date).fillna(0.0).values
    except (OSError, ValueError, KeyError):
        return [ATH_REZERVA[1] if d >= ATH_REZERVA[0] else 0.0 for d in date]


def adauga_indicatori(df):
    df = df.copy()
    df['SMA_50'] = df['Close'].rolling(window=50).mean()
    df['Local_High'] = df['High'].rolling(window=20, center=False).max()
    df['Cycle_Peak_90d'] = df['High'].rolling(window=90, min_periods=1).max()
    df['Z_Max_45d'] = df['Master_Index'].rolling(window=45).max()
    # [regula 5] ATH nou în ultimele 90 de zile: vârful pe 90 de zile e chiar ATH-ul de până azi
    df['ATH'] = pd.Series(_ath_istoric(df['Data'].astype(str)), index=df.index).combine(df['High'].cummax(), max)
    varf_ath = df['High'].rolling(window=FEREASTRA_ATH, min_periods=1).max()
    df['ATH_Nou_90d'] = varf_ath >= df['ATH']
    df['Z_Ieri'] = df['Master_Index'].shift(1)   # [regula 6] pentru a detecta ziua în care Z trece sub prag
    return df


def reintrare_rapida(state, azi):
    """[regula 6] Cumpărare permisă în pauza de 7 zile: Z sub REINTRARE_Z (cel mult o dată pe zi)."""
    z = azi.get('Master_Index', 0)
    if not REINTRARE_MOD or z >= REINTRARE_Z or state["zile_de_la_buy"] < 1:
        return False
    if REINTRARE_MOD == 'traversare':
        z_ieri = azi.get('Z_Ieri', float('nan'))
        return not (z_ieri < REINTRARE_Z)          # ieri era peste prag (sau lipsește) -> azi l-a traversat
    return True


def prag_euforie(azi, v2=True):
    """Pragul Master_Index care armează alerta de top: +1.0 după un ATH nou în ultimele 90 de zile, altfel +1.5."""
    return PRAG_Z_EUFORIE_ATH if (v2 and bool(azi.get('ATH_Nou_90d', False))) else PRAG_Z_EUFORIE


def _cumpara(state, alocare, pret):
    state["btc"] += alocare / pret
    state["cash"] -= alocare
    state["total_investit"] += alocare
    state["ultimul_pret_buy"] = pret
    state["zile_de_la_buy"] = 0


def decide(state, azi, v2=True):
    """
    Logica de decizie pentru O zi (rândul `azi`, cu indicatorii deja calculați).
    Modifică `state` și returnează lista de mesaje (acțiuni executate / evenimente).
    v2=False rulează regulile originale (pentru comparație în backtest).
    """
    mesaje = []
    pret = azi['Close']
    z_score_raw = azi.get('Master_Index', 0)
    mvrv_ajustat = azi.get('Adjusted_MVRV', 0)
    fost_high = azi.get('Local_High', 0)
    cycle_peak = azi.get('Cycle_Peak_90d', pret)
    sma_50 = azi.get('SMA_50', pret)
    drawdown_de_la_peak = (cycle_peak - pret) / cycle_peak

    # Regulile (7/14 zile) sunt în ZILE: contorul crește doar cu zilele noi de date, nu cu fiecare rulare.
    zi_date = azi['Data']
    zile_noi = zile_intre(state.get("ultima_rulare"), zi_date) if state.get("ultima_rulare") not in (None, "N/A") else 1
    state["zile_de_la_buy"] += zile_noi
    state["ultima_rulare"] = zi_date

    if pret > fost_high * 1.02 and fost_high > state["nivel_suport_curent"]:
        state["nivel_suport_curent"] = fost_high

    pret_mediu = (state["total_investit"] / state["btc"]) if state["btc"] > 0 else 0.0
    actiune_executata = False

    # [experimental, dezactivat] FALS TOP: prețul a depășit vârful la care am vândut
    if v2 and IESIRE_FALS_TOP and state["interdictie_macro_activa"] and state["btc"] == 0 \
            and state["macro_top_trecut"] > 0 and pret > state["macro_top_trecut"]:
        state["interdictie_macro_activa"] = False
        state["distributie_finala_activa"] = False
        state["prima_intrare_facuta"] = False
        state["profit_lock_activ"] = False
        mesaje.append(f"[!] FALS TOP (Z: {z_score_raw:+.2f}) | Prețul a depășit vârful vândut "
                      f"(${state['macro_top_trecut']:,.0f}). Reluăm acumularea!")

    # MACRO RESET (bear market: -40% de la vârful ciclului)
    if state["interdictie_macro_activa"]:
        if v2:
            # [v2] vârful ciclului = cel mai mare preț atins, nu prețul la care am vândut.
            # v1 măsura -40% față de vârful vândut; dacă piața urca mai sus după vânzare,
            # pragul nu mai era atins niciodată și botul rămânea pe cash pentru totdeauna.
            state["ultimul_peak_cunoscut"] = max(state["ultimul_peak_cunoscut"], azi.get('High', pret))
        if pret <= state["ultimul_peak_cunoscut"] * 0.60:
            state["interdictie_macro_activa"] = False
            state["distributie_finala_activa"] = False
            mesaje.append(f"[!] BEAR MARKET RESET (Z: {z_score_raw:+.2f}) | Prețul a corectat 40% de la vârful "
                          f"ciclului (${state['ultimul_peak_cunoscut']:,.0f}). Începem acumularea!")
            state["prima_intrare_facuta"] = False; state["profit_lock_activ"] = False
            if v2:
                # [v2] ciclu nou: alerta de euforie din ciclul trecut nu mai e valabilă
                # (în v1 rămânea armată și botul vindea 70% a doua zi după reacumulare)
                state["alerta_rosie_euforie"] = False

    # DIAMOND HANDS
    bull_run_activ = (pret > pret_mediu * 1.30) and state["btc"] > 0
    if bull_run_activ and not state["profit_lock_activ"] and not state["interdictie_macro_activa"]:
        state["profit_lock_activ"] = True
        mesaje.append(f"[!] DIAMOND HANDS ACTIVAT (Z: {z_score_raw:+.2f}) | Păstrăm totul către ATH!")

    if state["profit_lock_activ"] and (z_score_raw < -1.0 or state["btc"] == 0):
        state["profit_lock_activ"] = False
        if state["btc"] > 0: mesaje.append(f"[!] DIAMOND HANDS DEZACTIVAT (Z: {z_score_raw:+.2f}) | Capitulare.")

    # TOP CONFIRMAT & ATH BREAKER  ([v2] + confirmare on-chain: MVRV în treimea de sus a benzii)
    confirmare_onchain = (mvrv_ajustat >= PRAG_MVRV_TOP) if v2 else True
    if z_score_raw >= prag_euforie(azi, v2) and confirmare_onchain \
            and (state["macro_top_trecut"] == 0 or pret >= state["macro_top_trecut"]):
        state["alerta_rosie_euforie"] = True

    trend_epuizat = state["alerta_rosie_euforie"] and (drawdown_de_la_peak >= 0.10 or pret < sma_50)

    # --- VÂNZĂRI ---
    if trend_epuizat and pret >= pret_mediu and not state["distributie_finala_activa"] and state["btc"] > 0:
        btc_de_vandut = state["btc"] * 0.70
        incasare = btc_de_vandut * pret
        state["cash"] += incasare; state["btc"] -= btc_de_vandut; state["total_investit"] -= (btc_de_vandut * pret_mediu)
        state["pret_vanzare_70"] = pret
        mesaje.append(f"🔴 SELL MACRO TOP 70% | Z-Score: {z_score_raw:+.2f} | MVRV adj {mvrv_ajustat:.2f} | "
                      f"Vândut: ${incasare:,.2f} la prețul ${pret:,.2f}")
        state["interdictie_macro_activa"] = True; state["ultimul_peak_cunoscut"] = cycle_peak
        state["macro_top_trecut"] = cycle_peak; state["alerta_rosie_euforie"] = False
        state["distributie_finala_activa"] = True; actiune_executata = True

    elif state["distributie_finala_activa"] and state["btc"] > 0:
        if pret >= state["pret_vanzare_70"] * 1.20:
            incasare = state["btc"] * pret
            state["cash"] += incasare
            mesaje.append(f"🚀 SELL MOONBAG FOMO +20% | Z-Score: {z_score_raw:+.2f} | Încasat: ${incasare:,.2f}")
            state["btc"] = 0; state["total_investit"] = 0; state["distributie_finala_activa"] = False; actiune_executata = True

        elif pret < state["pret_vanzare_70"] * 0.78:
            incasare = state["btc"] * pret
            state["cash"] += incasare
            mesaje.append(f"⚠️ SELL MOONBAG PANIC -22% | Z-Score: {z_score_raw:+.2f} | Încasat: ${incasare:,.2f}")
            state["btc"] = 0; state["total_investit"] = 0; state["distributie_finala_activa"] = False; actiune_executata = True

    # [v2] RĂSCUMPĂRARE LA REDUCERE: după o vânzare de top, dacă piața capitulează (Master_Index < -0.5)
    # la un preț cu cel puțin RASCUMPARARE_REDUCERE sub prețul la care am vândut, cumpărăm înapoi mai ieftin
    # (40% din cash la fiecare semnal), fără să mai așteptăm -40% de la vârf.
    rascumparare = (v2 and RASCUMPARARE_REDUCERE and state["interdictie_macro_activa"]
                    and state["pret_vanzare_70"] > 0 and z_score_raw < -0.5
                    and pret <= state["pret_vanzare_70"] * (1 - RASCUMPARARE_REDUCERE))

    # --- CUMPĂRĂRI ---
    if not actiune_executata and ((not state["interdictie_macro_activa"] and not state["profit_lock_activ"]) or rascumparare):
        if z_score_raw < -0.5:
            if state["zile_de_la_buy"] >= 7 or reintrare_rapida(state, azi) \
                    or (REINTRARE_PASTREAZA_10 and pret <= state["ultimul_pret_buy"] * 0.90):
                procent = 0.70 if (not state["prima_intrare_facuta"] and not rascumparare) else 0.40
                alocare = min(state["cash"] * procent, state["cash"])
                if alocare > 10:
                    _cumpara(state, alocare, pret)
                    if rascumparare:
                        mesaje.append(f"🟢 BUY RĂSCUMPĂRARE | Cumpărat ${alocare:,.2f} la ${pret:,.2f} "
                                      f"({(pret / state['pret_vanzare_70'] - 1):.0%} față de vânzarea de la ${state['pret_vanzare_70']:,.0f})")
                    elif not state["prima_intrare_facuta"]:
                        mesaje.append(f"🔥 BUY FRONT-LOAD MASIV | Cumpărat ${alocare:,.2f} la ${pret:,.2f}")
                        state["prima_intrare_facuta"] = True
                    else:
                        mesaje.append(f"🟢 BUY AGRESIV DCA | Cumpărat ${alocare:,.2f} la ${pret:,.2f}")

        elif -0.5 <= z_score_raw < 0.0:
            if state["zile_de_la_buy"] >= 14 or pret <= state["ultimul_pret_buy"] * 0.95:
                alocare = min(state["cash"] * 0.10, state["cash"])
                if alocare > 10:
                    _cumpara(state, alocare, pret)
                    mesaje.append(f"🟢 BUY MICRO DCA | Cumpărat ${alocare:,.2f} la ${pret:,.2f}")

        elif 0.0 <= z_score_raw < 1.0:
            if state["nivel_suport_curent"] > 0 and (state["nivel_suport_curent"] * 0.95 <= pret <= state["nivel_suport_curent"] * 1.05) and state["zile_de_la_buy"] > 7:
                alocare = min(state["cash"] * 0.20, state["cash"])
                if alocare > 10:
                    _cumpara(state, alocare, pret)
                    mesaje.append(f"🟢 BUY S/R BOUNCE | Cumpărat ${alocare:,.2f} la ${pret:,.2f}")

    return mesaje
