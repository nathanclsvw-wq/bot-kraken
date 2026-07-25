import ccxt
import pandas as pd
import numpy as np
import time

# Initialisation de Kraken (remplace par tes vraies clés API)
exchange = ccxt.kraken({
    'apiKey': 'Vhz+LZ1KFKuZv8E4vAvgDrxpO2bnhmqZl2UQlAlLi5HYSrBDV/sqV+Fm',
    'secret': ' JE5xHOtVCzVgnMx0fzv+qBnm682tdlBo2n7ni0bRmmCQhnA097QB3RCkOI9qVEp6LRiK/1bLdlD0XGkr376zgg==',
    'enableRateLimit': True,
})

# Paramètres de l'algorithme Live
SYMBOL = 'BTC/EUR'
TIMEFRAME = '1h'
FEE = 0.003  # 0.3% de frais

# Configuration V7 (basée sur ton backtest)
L_VOL_TARGET = 10000
L_DIST_THRESH = 1.001
L_SMA_P = 100
L_TP = 0.12     # +12% de Take Profit
L_SL = -0.006   # -0.6% de Stop Loss
STAKE_EUR = 5.0 # Montant par trade

def run_live_bot():
    print("--- Démarrage du Bot Live V7 avec TP/SL ---")
    active_position = False
    entry_price = 0.0
    current_sl = 0.0

    while True:
        try:
            # Récupération des bougies en direct depuis Kraken
            ohlcv = exchange.fetch_ohlcv(SYMBOL, timeframe=TIMEFRAME, limit=150)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            
            C = df['close'].values
            V = df['volume'].values
            
            # Calculs des indicateurs en direct
            sma_l = pd.Series(C).rolling(window=L_SMA_P).mean().values
            cv = np.cumsum(V)
            idx_l = np.where(np.diff(cv // L_VOL_TARGET) > 0)[0] + 1
            
            current_price = C[-1]
            current_sma = sma_l[-1]
            
            print(f"[{pd.Timestamp.now()}] Prix : {current_price:.2f} EUR | SMA 100 : {current_sma:.2f} EUR")

            # 1. SI AUCUNE POSITION N'EST ACTIVE : On cherche le signal d'achat
            if not active_position:
                # Vérification de la condition de l'algo
                if C[-1] / current_sma > L_DIST_THRESH:
                    print(">>> SIGNAL LONG DÉTECTÉ : Achat en cours...")
                    balance = exchange.fetch_balance()
                    eur_free = balance['free'].get('EUR', 0)
                    
                    if eur_free >= STAKE_EUR:
                        btc_amount = STAKE_EUR / current_price
                        order = exchange.create_market_buy_order(SYMBOL, btc_amount)
                        
                        entry_price = current_price
                        current_sl = entry_price * (1 + L_SL)
                        active_position = True
                        print(f"Position ouverte à {entry_price:.2f} EUR | SL initial : {current_sl:.2f}")
                    else:
                        print("Fonds EUR insuffisants sur le compte.")
                else:
                    print("-> Statut : Calme (Pas de signal).")

            # 2. SI UNE POSITION EST ACTIVE : On surveille le TP et le SL en temps réel
            else:
                pnl_pct = (current_price - entry_price) / entry_price
                print(f"-> Position active | Entrée : {entry_price:.2f} | PnL actuel : {pnl_pct*100:+.2f}%")

                # Vérification Take Profit (+12%) ou Stop Loss (-0.6%)
                if current_price >= entry_price * (1 + L_TP):
                    print(">>> TAKE PROFIT ATTEINT (+12%) ! Vente de la position.")
                    balance = exchange.fetch_balance()
                    btc_free = balance['free'].get('BTC', 0)
                    if btc_free > 0:
                        exchange.create_market_sell_order(SYMBOL, btc_free)
                    active_position = False
                    
                elif current_price <= current_sl:
                    print(">>> STOP LOSS ATTEINT (-0.6%) ! Coupure des pertes.")
                    balance = exchange.fetch_balance()
                    btc_free = balance['free'].get('BTC', 0)
                    if btc_free > 0:
                        exchange.create_market_sell_order(SYMBOL, btc_free)
                    active_position = False

        except Exception as e:
            print(f"Erreur rencontrée : {e}")

        # Pause d'une heure avant de vérifier la bougie suivante
        time.sleep(3600)

run_live_bot()
