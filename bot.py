import ccxt
import time

# Configuration de l'échange Kraken
exchange = ccxt.kraken({
    'apiKey': 'Vhz+LZ1KFKuZv8E4vAvgDrxpO2bnhmqZl2UQlAlLi5HYSrBDV/sqV+Fm',
    'secret': ' JE5xHOtVCzVgnMx0fzv+qBnm682tdlBo2n7ni0bRmmCQhnA097QB3RCkOI9qVEp6LRiK/1bLdlD0XGkr376zgg==',
    'enableRateLimit': True,
})

SYMBOL = 'BTC/EUR'

def test_short_margin():
    print("==================================================")
    print("--- TEST D'OUVERTURE DE POSITION SHORT (MARGE) ---")
    print("==================================================")
    
    try:
        # 1. Récupération du prix actuel
        ticker = exchange.fetch_ticker(SYMBOL)
        current_price = ticker['last']
        print(f"Prix actuel BTC/EUR : {current_price:.2f} €")

        # Kraken exige un montant minimum de 0.0001 BTC
        amount_btc = 0.0001
        trade_value_eur = amount_btc * current_price
        print(f"Montant du trade : {amount_btc} BTC (~{trade_value_eur:.2f} €)")

        # 2. Envoi de l'ordre SHORT en marge avec levier x2 (Marge Kraken sur CCXT)
        print("\n1. Envoi de l'ordre de VENTE A DECOUVERT (Short)...")
        order = exchange.create_market_sell_order(
            SYMBOL, 
            amount_btc, 
            params={'leverage': 2}  # Clé CCXT pour activer la Marge sur Kraken
        )
        
        order_id = order['id']
        print(f"✅ Ordre envoyé avec succès ! ID Ordre : {order_id}")

        # 3. Confirmation de l'exécution
        time.sleep(2)
        order_info = exchange.fetch_order(order_id, SYMBOL)
        exec_price = order_info.get('average') or order_info.get('price') or current_price
        print(f"Statut : {order_info.get('status')} | Prix d'exécution : {exec_price} €")

        print("\n--------------------------------------------------")
        print("👉 VA SUR TON INTERFACE KRAKEN PRO (SITE WEB/APP) :")
        print("1. Regarde dans l'onglet 'Positions' (ou 'Open Positions').")
        print("2. Tu dois voir une position SHORT ouverte sur BTC/EUR.")
        print("--------------------------------------------------")

        # Pause pour te laisser le temps de vérifier dans l'interface
        input("\n[APPUIS SUR ENTRÉE UNE FOIS QUE TU AS VÉRIFIÉ POUR FERMER LE SHORT]")

        # 4. Rachat pour fermer la position Short
        print("\n2. Fermeture de la position SHORT (Rachat)...")
        close_order = exchange.create_market_buy_order(
            SYMBOL, 
            amount_btc, 
            params={'leverage': 2}
        )
        print(f"✅ Position Short fermée avec succès ! ID Ordre : {close_order['id']}")

    except ccxt.ExchangeError as ee:
        print(f"\n❌ Erreur API Kraken : {ee}")
        print("Vérifie que la Marge est autorisée sur la paire BTC/EUR dans ton compte Kraken.")
    except Exception as e:
        print(f"\n❌ Erreur inattendue : {e}")

if __name__ == "__main__":
    test_short_margin()
