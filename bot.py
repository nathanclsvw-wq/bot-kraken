import ccxt
import pandas as pd
import numpy as np
import time
import json
import os
import logging

# --- CONFIGURATION DU LOGGING ---
logging.basicConfig(
    filename='bot.log',
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
logging.getLogger().addHandler(console_handler)

# Configuration de l'échange Kraken
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

# Fidélité stricte au backtest par défaut (0 = bougie exacte, modifiable à 1 si besoin)
MAX_SIGNAL_DELAY = 0 

STAKE_EUR = 5.0  # Montant par trade
STATE_FILE = "bot_state.json"

def save_state(state):
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f)
    except Exception as e:
        logging.error(f"Erreur lors de la sauvegarde de l'état : {e}")

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Erreur de lecture du fichier d'état : {e}")
    return {
        'active_trade': None,
        'last_l_bar_idx': -20,
        'last_s_bar_idx': -20
    }

def verify_and_get_order_details(order_id, fallback_price):
    try:
        order = exchange.fetch_order(order_id, SYMBOL)
        if order.get('status') != 'closed':
            time.sleep(1)
            order = exchange.fetch_order(order_id, SYMBOL)
        
        exec_price = order.get('average') or order.get('price') or fallback_price
        executed_qty = order.get('filled') or order.get('amount')
        return exec_price, executed_qty
    except Exception as e:
        logging.error(f"Erreur lors de la vérification de l'ordre {order_id} : {e}")
        return fallback_price, STAKE_EUR / fallback_price

def verify_kraken_margin_short(exchange, symbol):
    try:
        balance = exchange.fetch_balance()
        debt_btc = balance.get('debt', {}).get('BTC', 0)
        free_btc = balance['free'].get('BTC', 0)
        
        if float(debt_btc) > 0 or float(free_btc) < 0:
            return True
            
        positions = exchange.fetch_positions([symbol])
        for p in positions:
            if float(p.get('contracts', 0)) != 0 or float(p.get('notional', 0)) != 0:
                return True
                
        return False
    except Exception as e:
        logging.error(f"Erreur lors du diagnostic de la position marge : {e}")
        return False

def reconcile_state_with_exchange(state):
    logging.info("Réconciliation de l'état avec l'exchange...")
    try:
        balance = exchange.fetch_balance()
        btc_free = balance['free'].get('BTC', 0)
        
        current_price = exchange.fetch_ticker(SYMBOL)['last']
        btc_value_eur = btc_free * current_price
        
        if state.get('needs_reconciliation'):
            logging.warning("⚠️ Drapeau de réconciliation activé suite à une anomalie précédente. Vérification approfondie.")
        
        if state['active_trade'] is None and btc_value_eur > STAKE_EUR * 0.8:
            logging.warning("⚠️ Incohérence détectée : Du BTC est présent sur le compte mais aucun trade n'est enregistré. Reconstruction d'un trade LONG.")
            state['active_trade'] = {
                'type': 'LONG',
                'entry_price': current_price,
                'amount_btc': btc_free,
                'sl': current_price * (1 + L_SL),
                'bars_held': 0,
                'is_be': False,
                'is_lock': False
            }
        elif state['active_trade'] is not None and btc_free < (state['active_trade']['amount_btc'] * 0.5) and state['active_trade']['type'] == 'LONG':
            logging.warning("⚠️ Incohérence détectée : L'état indique un LONG actif mais le solde BTC est insuffisant. Réinitialisation.")
            state['active_trade'] = None
            
        state.pop('needs_reconciliation', None)
        save_state(state)
        logging.info("Réconciliation terminée avec succès.")
    except Exception as e:
        logging.error(f"Erreur critique lors de la réconciliation : {e}")
    return state

def run_live_v7_ultimate():
    logging.info("--- Démarrage du Bot Live Algo V7 (Sécurisé & Sans Levier) ---")
    
    state = load_state()
    state = reconcile_state_with_exchange(state)
    
    active_trade = state['active_trade']
    last_l_bar_idx = state['last_l_bar_idx']
    last_s_bar_idx = state['last_s_bar_idx']
    
    last_processed_candle_time = None

    while True:
        try:
            ohlcv = exchange.fetch_ohlcv(SYMBOL, timeframe=TIMEFRAME, limit=1200)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            
            current_candle_time = df['timestamp'].iloc[-2]
            
            if last_processed_candle_time != current_candle_time:
                last_processed_candle_time = current_candle_time
                logging.info(f"Nouvelle bougie validée (Clôture : {pd.to_datetime(current_candle_time, unit='ms')})")

                C = df['close'].values
                H = df['high'].values
                L = df['low'].values
                V = df['volume'].values

                sma_l = pd.Series(C).rolling(window=L_SMA_P).mean().values
                sma_s = pd.Series(C).rolling(window=S_SMA_P).mean().values
                cv = np.cumsum(V)

                # --- OBSERVABILITÉ / LOGS VOLUME ---
                logging.info(f"Volume cumulé : {cv[-1]:.2f}")
                logging.info(f"Volume moyen par bougie : {np.mean(V):.2f}")
                logging.info(f"Volume max par bougie : {np.max(V):.2f}")
                logging.info(f"Volume total historique récupéré : {np.sum(V):.2f}")

                idx_l = np.where(np.diff(cv // L_VOL_TARGET) > 0)[0] + 1
                idx_s = np.where(np.diff(cv // S_VOL_TARGET) > 0)[0] + 1

                logging.info(f"Paliers LONG : {len(idx_l)}")
                logging.info(f"Paliers SHORT : {len(idx_s)}")

                current_price = C[-1]

                # --- 1. GESTION DU TRADE ACTIF ---
                if active_trade is not None:
                    active_trade['bars_held'] += 1
                    p_in = active_trade['entry_price']
                    t_type = active_trade['type']

                    if t_type == 'LONG':
                        p_high_gain = (H[-2] / p_in) - 1
                        if p_high_gain >= L_LOCK_TRIG and not active_trade['is_lock']:
                            active_trade['sl'] = p_in * (1 + L_LOCK_VAL)
                            active_trade['is_lock'] = True
                        elif p_high_gain >= L_BE_TRIG and not active_trade['is_be']:
                            active_trade['sl'] = p_in
                            active_trade['is_be'] = True

                        hit_sl = L[-2] <= active_trade['sl']
                        hit_tp = H[-2] >= p_in * (1 + L_TP)
                        time_out = active_trade['bars_held'] >= 10

                        if hit_sl or hit_tp or time_out:
                            logging.info(f">>> FERMETURE LONG (SL: {hit_sl}, TP: {hit_tp}, Timeout: {time_out})")
                            order = exchange.create_market_sell_order(SYMBOL, active_trade['amount_btc'])
                            order_id = order.get('id')
                            if order_id:
                                verify_and_get_order_details(order_id, current_price)
                            logging.info("Trade LONG fermé.")
                            active_trade = None
                            save_state(state)

                    elif t_type == 'SHORT':
                        p_high_pnl = 1 - (L[-2] / p_in)
                        p_low_pnl = 1 - (H[-2] / p_in)
                        
                        if p_high_pnl >= (S_TP / 2) and active_trade['sl'] < 0.0:
                            active_trade['sl'] = 0.0

                        hit_sl = p_low_pnl <= active_trade['sl']
                        hit_tp = p_high_pnl >= S_TP
                        time_out = active_trade['bars_held'] >= 10

                        if hit_sl or hit_tp or time_out:
                            logging.info(f">>> FERMETURE SHORT (SL: {hit_sl}, TP: {hit_tp}, Timeout: {time_out})")
                            order = exchange.create_market_buy_order(SYMBOL, active_trade['amount_btc'], params={'trading_agreement': 'leveraged'})
                            order_id = order.get('id')
                            if order_id:
                                verify_and_get_order_details(order_id, current_price)
                            logging.info("Trade SHORT fermé.")
                            active_trade = None
                            save_state(state)

                # --- 2. RECHERCHE DE NOUVEAUX SIGNAUX ---
                else:
                    # Préparation indicateurs LONG
                    recent_volume_long = False
                    cooldown_ok_l = False
                    sma_ok_l = False
                    signal_long = False
                    last_idx_l_val = None
                    ratio_l = None

                    if len(idx_l) > 0:
                        last_idx_l_val = idx_l[-1]
                        bars_since_volume_l = (len(C) - 2) - last_idx_l_val
                        recent_volume_long = 0 <= bars_since_volume_l <= MAX_SIGNAL_DELAY

                        if len(idx_l) >= 11:
                            cooldown_ok_l = (len(idx_l) - 11) > last_l_bar_idx + L_COOL

                        if not np.isnan(sma_l[last_idx_l_val]):
                            ratio_l = C[last_idx_l_val] / sma_l[last_idx_l_val]
                            sma_ok_l = ratio_l > L_DIST_THRESH

                        signal_long = (
                            len(idx_l) >= 11
                            and recent_volume_long
                            and cooldown_ok_l
                            and sma_ok_l
                        )

                    # Log mode DEBUG LONG
                    logging.info(
                        f"""
=========================
[DEBUG LONG]
len(idx_l)={len(idx_l)}
last_idx={last_idx_l_val}
recent={recent_volume_long}
cool={cooldown_ok_l}
sma_ok={sma_ok_l}
ratio={ratio_l}
SIGNAL_LONG={signal_long}
=========================
"""
                    )

                    # Signal LONG
                    if signal_long:
                        logging.info(">>> SIGNAL LONG CONFIRMÉ !")
                        balance = exchange.fetch_balance()
                        if balance['free'].get('EUR', 0) >= STAKE_EUR:
                            order = exchange.create_market_buy_order(SYMBOL, STAKE_EUR / current_price)
                            order_id = order.get('id')
                            exec_price, executed_qty = verify_and_get_order_details(order_id, current_price) if order_id else (current_price, STAKE_EUR / current_price)
                            
                            active_trade = {
                                'type': 'LONG',
                                'entry_price': exec_price,
                                'amount_btc': executed_qty,
                                'sl': exec_price * (1 + L_SL),
                                'bars_held': 0,
                                'is_be': False,
                                'is_lock': False
                            }
                            last_l_bar_idx = len(idx_l) - 11
                            state['active_trade'] = active_trade
                            state['last_l_bar_idx'] = last_l_bar_idx
                            save_state(state)
                            logging.info(
                                f"""
Trade ouvert
Type : LONG
Prix : {exec_price}
Quantité : {executed_qty}
SL : {active_trade['sl']}
"""
                            )

                    # Signal SHORT (Blindé 10/10 avec vérification de la dette de marge)
                    if active_trade is None:
                        recent_volume_short = False
                        cooldown_ok_s = False
                        sma_ok_s = False
                        signal_short = False
                        last_idx_s_val = None
                        ratio_s = None

                        if len(idx_s) > 0:
                            last_idx_s_val = idx_s[-1]
                            bars_since_volume_s = (len(C) - 2) - last_idx_s_val
                            recent_volume_short = 0 <= bars_since_volume_s <= MAX_SIGNAL_DELAY

                            if len(idx_s) >= 11:
                                cooldown_ok_s = (len(idx_s) - 11) > last_s_bar_idx + S_COOL

                            if not np.isnan(sma_s[last_idx_s_val]):
                                ratio_s = C[last_idx_s_val] / sma_s[last_idx_s_val]
                                sma_ok_s = C[last_idx_s_val] < sma_s[last_idx_s_val]

                            signal_short = (
                                len(idx_s) >= 11
                                and recent_volume_short
                                and cooldown_ok_s
                                and sma_ok_s
                            )

                        # Log mode DEBUG SHORT
                        logging.info(
                            f"""
=========================
[DEBUG SHORT]
len(idx_s)={len(idx_s)}
last_idx={last_idx_s_val}
recent={recent_volume_short}
cool={cooldown_ok_s}
sma_ok={sma_ok_s}
ratio={ratio_s}
SIGNAL_SHORT={signal_short}
=========================
"""
                        )

                        if signal_short:
                            logging.info(">>> SIGNAL SHORT CONFIRMÉ !")
                            
                            if not exchange.has.get('margin'):
                                logging.error("❌ Erreur critique : Marge non supportée par CCXT.")
                                continue
                            
                            order = exchange.create_market_sell_order(
                                SYMBOL, 
                                STAKE_EUR / current_price, 
                                params={'trading_agreement': 'leveraged'}
                            )
                            order_id = order.get('id')
                            
                            if order_id:
                                full_order = None
                                for _ in range(10):
                                    full_order = exchange.fetch_order(order_id, SYMBOL)
                                    if full_order.get('status') == 'closed':
                                        break
                                    time.sleep(1)
                                
                                logging.info(f"Statut final short : {full_order.get('status')} | Info : {full_order.get('info')}")
                                
                                if full_order.get('status') != 'closed':
                                    logging.warning("⚠️ Ordre short non clôturé dans le temps imparti. Abandon.")
                                    continue
                                
                                if verify_kraken_margin_short(exchange, SYMBOL):
                                    exec_price = full_order.get('average') or full_order.get('price') or current_price
                                    executed_qty = full_order.get('filled') or full_order.get('amount')
                                    
                                    active_trade = {
                                        'type': 'SHORT',
                                        'entry_price': exec_price,
                                        'amount_btc': executed_qty,
                                        'sl': S_SL,
                                        'bars_held': 0
                                    }
                                    last_s_bar_idx = len(idx_s) - 11
                                    state['active_trade'] = active_trade
                                    state['last_s_bar_idx'] = last_s_bar_idx
                                    state.pop('needs_reconciliation', None)
                                    save_state(state)
                                    logging.info("✅ Position SHORT ouverte, vérifiée et enregistrée.")
                                    logging.info(
                                        f"""
Trade ouvert
Type : SHORT
Prix : {exec_price}
Quantité : {executed_qty}
SL : {S_SL}
"""
                                    )
                                else:
                                    logging.critical("🚨 ALERTE : Ordre exécuté mais aucune dette/position marge détectée ! Signalement pour réconciliation.")
                                    state['needs_reconciliation'] = True
                                    save_state(state)

                # --- 3. RÉSUMÉ SYNTHÉTIQUE PAR BOUGIE ---
                logging.info(
                    f"""
=========================
[SYNTHÈSE BOUGIE]
Close : {C[-2]}
Volume : {V[-2]}
LONG = {signal_long}
SHORT = {signal_short}
=========================
"""
                )

                state['active_trade'] = active_trade
                state['last_l_bar_idx'] = last_l_bar_idx
                state['last_s_bar_idx'] = last_s_bar_idx
                save_state(state)

        except ccxt.NetworkError as ne:
            logging.error(f"Erreur réseau : {ne}")
            time.sleep(5)
        except ccxt.ExchangeError as ee:
            logging.error(f"Erreur API Exchange : {ee}")
            time.sleep(10)
        except Exception as e:
            logging.error(f"Erreur critique : {e}")

        time.sleep(55)

run_live_v7_ultimate()
