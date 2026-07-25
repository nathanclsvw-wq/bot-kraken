import ccxt
import pandas as pd
import numpy as np
import time

# Configuration de l'échange Kraken (mets tes clés ici)
exchange = ccxt.kraken({
    'apiKey': 'Vhz+LZ1KFKuZv8E4vAvgDrxpO2bnhmqZl2UQlAlLi5HYSrBDV/sqV+Fm',
    'secret': ' JE5xHOtVCzVgnMx0fzv+qBnm682tdlBo2n7ni0bRmmCQhnA097QB3RCkOI9qVEp6LRiK/1bLdlD0XGkr376zgg==',
    'enableRateLimit': True,
})

SYMBOL = 'BTC/EUR'
TIMEFRAME = '1h'
FEE = 0.003  # 0.3% de frais

# --- PARAMÈTRES EXACTS DE L'ALGO V7 ---
L_VOL_TARGET, L_DIST_THRESH, L_SMA_P = 10000, 1.001, 100
L_TP, L_SL = 0.12, -0.006
L_BE_TRIG, L_LOCK_TRIG, L_LOCK_VAL = 0.008, 0.024, 0.023
L_COOL = 3

S_VOL_TARGET, S_SMA_P = 25000, 1000
S_TP, S_SL = 0.12, -0.006
S_COOL = 5

STAKE_EUR = 5.0  # Montant par trade

def run_live_v7():
    print("--- Démarrage du Bot Live Algo V7 (Long & Short) ---")
    
    # Suivi des états en live pour respecter le cooldown et la durée de 10 bougies
    active_trade = None  # {'type': 'LONG'/'SHORT', 'entry_price': float, 'sl': float, 'bars_held': int, 'is_be': bool, 'is_lock': bool}
    last_l_bar_idx = -20
    last_s_bar_idx = -20
    bar_counter = 0

    while True:
        try:
            # Récupération des données en direct (assez pour la SMA 1000 des shorts)
            ohlcv = exchange.fetch_ohlcv(SYMBOL, timeframe=TIMEFRAME, limit=1200)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            
            C = df['close'].values
            H = df['high'].values
            L = df['low'].values
            V = df['volume'].values

            # Calculs indicateurs identiques au backtest
            sma_l = pd.Series(C).rolling(window=L_SMA_P).mean().values
            sma_s = pd.Series(C).rolling(window=S_SMA_P).mean().values
            cv = np.cumsum(V)

            idx_l = np.where(np.diff(cv // L_VOL_TARGET) > 0)[0] + 1
            idx_s = np.where(np.diff(cv // S_VOL_TARGET) > 0)[0] + 1

            current_price = C[-1]
            print(f"[{pd.Timestamp.now()}] Prix BTC : {current_price:.2f} EUR")

            # --- SI UNE POSITION EST ACTIVE : Gestion du trade en cours (TP, SL, Break-Even, Durée max 10 bougies) ---
            if active_trade is not None:
                active_trade['bars_held'] += 1
                p_in = active_trade['entry_price']
                t_type = active_trade['type']

                if t_type == 'LONG':
                    # Vérification des déclencheurs de SL dynamique (Lock / Break-Even)
                    p_high_gain = (H[-1] / p_in) - 1
                    if p_high_gain >= L_LOCK_TRIG and not active_trade['is_lock']:
                        active_trade['sl'] = p_in * (1 + L_LOCK_VAL)
                        active_trade['is_lock'] = True
                    elif p_high_gain >= L_BE_TRIG and not active_trade['is_be']:
                        active_trade['sl'] = p_in
                        active_trade['is_be'] = True

                    # Vérification Sortie (SL, TP ou fin des 10 bougies)
                    hit_sl = L[-1] <= active_trade['sl']
                    hit_tp = H[-1] >= p_in * (1 + L_TP)
                    time_out = active_trade['bars_held'] >= 10

                    if hit_sl or hit_tp or time_out:
                        print(f">>> FERMETURE POSITION LONG (SL: {hit_sl}, TP: {hit_tp}, Timeout: {time_out})")
                        balance = exchange.fetch_balance()
                        btc_free = balance['free'].get('BTC', 0)
                        if btc_free > 0:
                            exchange.create_market_sell_order(SYMBOL, btc_free)
                        active_trade = None

                elif t_type == 'SHORT':
                    p_high_pnl = 1 - (L[-1] / p_in)
                    p_low_pnl = 1 - (H[-1] / p_in)
                    
                    if p_high_pnl >= (S_TP / 2) and active_trade['sl'] < 0.0:
                        active_trade['sl'] = 0.0  # Passage à BE pour le short

                    hit_sl = p_low_pnl <= active_trade['sl']
                    hit_tp = p_high_pnl >= S_TP
                    time_out = active_trade['bars_held'] >= 10

                    if hit_sl or hit_tp or time_out:
                        print(f">>> FERMETURE POSITION SHORT (SL: {hit_sl}, TP: {hit_tp}, Timeout: {time_out})")
                        balance = exchange.fetch_balance()
                        eur_free = balance['free'].get('EUR', 0)
                        if eur_free >= STAKE_EUR:
                            btc_amt = STAKE_EUR / current_price
                            exchange.create_market_buy_order(SYMBOL, btc_amt)  # Rachat pour fermer le short
                        active_trade = None

            # --- SI AUCUNE POSITION N'EST ACTIVE : Recherche de signaux ---
            else:
                # Vérification signal LONG
                if len(idx_l) > 0:
                    last_idx_l_val = idx_l[-1]
                    if last_idx_l_val == len(C) - 2 and bar_counter != last_idx_l_val:
                        if len(idx_l) >= 11 and (len(idx_l) - 11) > last_l_bar_idx + L_COOL:
                            if C[last_idx_l_val] / sma_l[last_idx_l_val] > L_DIST_THRESH:
                                print(">>> SIGNAL LONG DÉTECTÉ !")
                                balance = exchange.fetch_balance()
                                if balance['free'].get('EUR', 0) >= STAKE_EUR:
                                    btc_amt = STAKE_EUR / current_price
                                    exchange.create_market_buy_order(SYMBOL, btc_amt)
                                    active_trade = {
                                        'type': 'LONG',
                                        'entry_price': current_price,
                                        'sl': current_price * (1 + L_SL),
                                        'bars_held': 0,
                                        'is_be': False,
                                        'is_lock': False
                                    }
                                    last_l_bar_idx = len(idx_l) - 11

                # Vérification signal SHORT
                if len(idx_s) > 0 and active_trade is None:
                    last_idx_s_val = idx_s[-1]
                    if last_idx_s_val == len(C) - 2:
                        if len(idx_s) >= 11 and (len(idx_s) - 11) > last_s_bar_idx + S_COOL:
                            if C[last_idx_s_val] < sma_s[last_idx_s_val]:
                                print(">>> SIGNAL SHORT DÉTECTÉ !")
                                balance = exchange.fetch_balance()
                                if balance['free'].get('EUR', 0) * current_price >= STAKE_EUR:
                                    btc_amt = STAKE_EUR / current_price
                                    exchange.create_market_sell_order(SYMBOL, btc_amt)
                                    active_trade = {
                                        'type': 'SHORT',
                                        'entry_price': current_price,
                                        'sl': S_SL,
                                        'bars_held': 0
                                    }
                                    last_s_bar_idx = len(idx_s) - 11

            bar_counter = len(C) - 2

        except Exception as e:
            print(f"Erreur d'exécution : {e}")

        # Attente d'une heure pour la bougie suivante
        time.sleep(3600)

run_live_v7()
