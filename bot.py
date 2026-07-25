import ccxt
import pandas as pd
import numpy as np
import time

# Initialisation de Kraken avec tes clés API
exchange = ccxt.kraken({
    'apiKey': 'Vhz+LZ1KFKuZv8E4vAvgDrxpO2bnhmqZl2UQlAlLi5HYSrBDV/sqV+Fm',
    'secret': ' JE5xHOtVCzVgnMx0fzv+qBnm682tdlBo2n7ni0bRmmCQhnA097QB3RCkOI9qVEp6LRiK/1bLdlD0XGkr376zgg==',
    'enableRateLimit': True,
})

def run_trading_bot():
    print("--- Démarrage du Bot V7 Live sur Railway ---")
    while True:
        try:
            # Récupération des bougies 1h
            ohlcv = exchange.fetch_ohlcv('BTC/EUR', timeframe='1h', limit=720)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            
            C = df['close'].values
            sma_l = pd.Series(C).rolling(window=100).mean().values
            
            current_price = C[-1]
            current_sma_l = sma_l[-1]
            
            print(f"[{pd.Timestamp.now()}] Prix : {current_price:.2f} EUR | SMA 100 : {current_sma_l:.2f} EUR")
            
            # Condition Long V7
            long_condition = (current_price / current_sma_l) > 1.001
            
            if long_condition:
                print(">>> SIGNAL LONG VALIDÉ !")
                balance = exchange.fetch_balance()
                eur_free = balance['free'].get('EUR', 0)
                target_stake = 5.0
                
                if eur_free >= target_stake:
                    btc_free = balance['free'].get('BTC', 0)
                    if (btc_free * current_price) < 2.0:
                        btc_amount = target_stake / current_price
                        order = exchange.create_market_buy_order('BTC/EUR', btc_amount)
                        print(f"ORDRE EXÉCUTÉ ! ID : {order['id']}")
                    else:
                        print("Position déjà active.")
                else:
                    print("Fonds EUR insuffisants.")
            else:
                print("-> Statut : Calme.")
                
        except Exception as e:
            print(f"Erreur : {e}")
            
        # Pause d'une heure
        time.sleep(3600)

run_trading_bot()