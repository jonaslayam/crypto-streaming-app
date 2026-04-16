import asyncio
import json
import logging
import os
import sys
import time
from dotenv import load_dotenv

DIRECTORIO_ACTUAL = os.path.dirname(os.path.abspath(__file__))
DIRECTORIO_PADRE = os.path.dirname(DIRECTORIO_ACTUAL)
sys.path.append(DIRECTORIO_PADRE)

from aiokafka import AIOKafkaConsumer
from database.oracle_manager import OracleManager

load_dotenv()

# Configuración de logging básica
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Clase auxiliar para la configuración de Oracle (requerida por OracleManager)
class OracleConfig:
    def __init__(self):
        self.user = os.getenv("ORACLE__USER")
        self.password = os.getenv("ORACLE__PASSWORD")
        self.dsn = os.getenv("ORACLE__DSN")

async def main():
    # --- Configuración Kafka ---
    KAFKA_BROKER = os.getenv("KAFKA_BROKER", "localhost:19092")
    TOPIC_NAME = "crypto-raw"
    GROUP_ID = f"latency-monitor-{int(time.time())}"

    # --- Inicialización de Oracle ---
    config = OracleConfig()
    oracle_mgr = OracleManager(config)
    loop = asyncio.get_running_loop()

    consumer = AIOKafkaConsumer(
        TOPIC_NAME,
        bootstrap_servers=KAFKA_BROKER,
        group_id=GROUP_ID,
        auto_offset_reset='latest',
        value_deserializer=lambda m: json.loads(m.decode('utf-8'))
    )

    logger.info("🚀 Iniciando monitor de latencia y persistencia en Oracle ADW...")
    await consumer.start()
    
    header = f"\n{'MONEDA':<12} | {'PRECIO':>15} | {'RED (ms)':>12} | {'INT (ms)':>10}"
    separator = "-" * len(header)
    
    print(separator)
    print(header)
    print(separator)

    msg_count = 0

    try:
        async for msg in consumer:
            now_ms = int(time.time() * 1000)
            data = msg.value
            
            # --- 1. Extracción de datos básicos ---
            event_time = data.get('event_time')
            ingest_time = data.get('ingest_time')
            symbol = data.get('symbol', 'N/A')
            close_price = data.get('close', 0.0)
            is_closed = data.get('is_closed', False)

            if not event_time:
                continue

            # --- 2. Cálculos de latencia (Lógica Original) ---
            net_latency = now_ms - event_time
            int_latency = now_ms - ingest_time if ingest_time else 0

            log_line = (
                f"{f'[{symbol}]':<12} | "
                f"{float(close_price):>15.4f} | "
                f"{net_latency:>12} | "
                f"{int_latency:>10}"
            )
            print(log_line)

            # --- 3. Persistencia en Oracle (Si la vela se cerró) ---
            if is_closed:
                # Preparamos el formato batch que espera OracleManager: (SYMBOL, OPEN_TIME, OPEN, HIGH, LOW, CLOSE, VOL, CLOSE_TIME, SOURCE)
                candle_payload = [(
                    symbol,
                    data.get('kline_open_time'),
                    data.get('open'),
                    data.get('high'),   
                    data.get('low'),
                    close_price,
                    data.get('volume'),
                    data.get('kline_close_time'),
                    "redpanda_live"
                )]
                
                # Ejecutamos en executor para no bloquear el loop de Kafka
                # insert_candles_batch es síncrono (usa oracledb)
                loop.run_in_executor(
                    None, 
                    oracle_mgr.insert_candles_batch, 
                    candle_payload
                )
            
            # Repetir cabecera cada 20 mensajes
            msg_count += 1
            if msg_count % 20 == 0:
                print(separator)
                print(header)
                print(separator)
            
    except Exception as e:
        logger.error(f"❌ Error en el procesamiento: {e}")
    finally:
        logger.info("🔌 Cerrando conexiones...")
        await consumer.stop()
        oracle_mgr.close() # Cerramos conexión a Oracle

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Monitor detenido por el usuario.")
