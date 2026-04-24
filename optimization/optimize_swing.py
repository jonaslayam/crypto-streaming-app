import optuna
import pandas as pd
import numpy as np
import time

def load_and_clean_data(filepath):
    print("📥 Cargando histórico en memoria...")
    df = pd.read_csv(filepath)
    
    # Mapeamos los nombres reales de tu CSV a variables más manejables
    # Asumimos que pred_72h es tu TARGET_RETURN_72H basado en tu muestra de datos
    df['pred_72h'] = df['TARGET_RETURN_72H'] 
    
    # Limpiamos las primeras filas que tienen NaN por el cálculo de las medias móviles (SMA_200)
    df = df.dropna(subset=['CLOSE_PRICE', 'SMA_200', 'RSI_14', 'ATR_14', 'pred_72h', 'RANGE_POS_48H'])
    
    return df

def simulate_trades(params, df_values):
    """
    Motor vectorizado ultra-rápido. 
    df_values es un diccionario de arrays de NumPy para saltarnos el overhead de Pandas.
    """
    steady_pred = params['steady_pred']
    steady_rsi = params['steady_rsi']
    steady_range = params['steady_range']
    
    volatile_pred = params['volatile_pred']
    volatile_rsi = params['volatile_rsi']
    volatile_range = params['volatile_range']
    
    exit_pred = params['exit_pred']
    sl_mult = params['sl_mult']
    
    # Arrays nativos
    prices = df_values['CLOSE_PRICE']
    sma_200 = df_values['SMA_200']
    rsi = df_values['RSI_14']
    ranges = df_values['RANGE_POS_48H']
    preds = df_values['pred_72h']
    atrs = df_values['ATR_14']
    symbols = df_values['SYMBOL']
    
    capital = 1000.0
    in_position = False
    entry_price = 0.0
    stop_loss = 0.0
    current_symbol = ""
    
    # Bucle optimizado
    for i in range(len(prices)):
        # Si cambiamos de moneda (ej. de ADAUSDT a BTCUSDT), cerramos posiciones fantasma
        if symbols[i] != current_symbol:
            in_position = False
            current_symbol = symbols[i]
            
        price = prices[i]
        
        if not in_position:
            # 1. STEADY_GROWTH (La apuesta segura)
            cond_steady = (preds[i] > steady_pred) and (price > sma_200[i]) and \
                          (ranges[i] < steady_range) and (rsi[i] < steady_rsi)
                          
            # 2. VOLATILE_REVERSAL (El especialista en rebotes)
            cond_volatile = (preds[i] > volatile_pred) and \
                            (ranges[i] < volatile_range) and (rsi[i] < volatile_rsi)
                            
            if cond_steady or cond_volatile:
                in_position = True
                entry_price = price
                stop_loss = price - (atrs[i] * sl_mult)
                
        else:
            # Trailing Stop Dinámico
            new_stop = price - (atrs[i] * sl_mult)
            if new_stop > stop_loss:
                stop_loss = new_stop
                
            # 3. SALIDA: El General ordena vender o toca el paracaídas
            if price <= stop_loss or preds[i] < exit_pred:
                profit_pct = (price - entry_price) / entry_price
                capital *= (1 + profit_pct)
                in_position = False
                
    return capital

# Variable global para acelerar Optuna (lee los datos una sola vez)
df_raw = load_and_clean_data("data/crypto_history.csv")
# Convertimos las columnas a un diccionario de arrays de NumPy
df_numpy = {col: df_raw[col].values for col in df_raw.columns}

def objective(trial):
    # Definimos las "perillas" que Optuna va a mover
    params = {
        # Reglas STEADY
        'steady_pred': trial.suggest_float('steady_pred', 0.8, 1.5),
        'steady_rsi': trial.suggest_int('steady_rsi', 45, 65),
        'steady_range': trial.suggest_float('steady_range', 0.30, 0.60),
        
        # Reglas VOLATILE
        'volatile_pred': trial.suggest_float('volatile_pred', 0.4, 0.9),
        'volatile_rsi': trial.suggest_int('volatile_rsi', 30, 55),
        'volatile_range': trial.suggest_float('volatile_range', 0.10, 0.30),
        
        # Reglas de SALIDA
        'exit_pred': trial.suggest_float('exit_pred', 0.1, 0.5),
        'sl_mult': trial.suggest_float('sl_mult', 1.0, 3.5)
    }
    
    return simulate_trades(params, df_numpy)

if __name__ == "__main__":
    print("🧠 Inicializando Optuna Engine...")
    start_time = time.time()
    
    # maxmimze: Queremos que la función devuelva la mayor cantidad de capital posible
    study = optuna.create_study(direction="maximize")
    
    # Ejecutamos 500 simulaciones. Puedes subir este número a 2000 si quieres una búsqueda más profunda.
    study.optimize(objective, n_trials=500)
    
    end_time = time.time()
    print(f"\n⏱️ Optimización completada en {round(end_time - start_time, 2)} segundos.")
    print("\n🏆 MEJORES PARÁMETROS ENCONTRADOS PARA DBT:")
    for key, value in study.best_params.items():
        # Formateo limpio para que lo copies directo a tu dbt_project.yml
        if isinstance(value, float):
            print(f"  {key}: {round(value, 3)}")
        else:
            print(f"  {key}: {value}")
            
    print(f"\n💰 Capital Final Proyectado (Desde $1000 base): ${round(study.best_value, 2)}")