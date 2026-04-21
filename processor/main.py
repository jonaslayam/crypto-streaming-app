import asyncio
import json
import logging
import os
import sys
import time
import datetime
import pytz
from dotenv import load_dotenv

DIRECTORIO_ACTUAL = os.path.dirname(os.path.abspath(__file__))
DIRECTORIO_PADRE = os.path.dirname(DIRECTORIO_ACTUAL)
sys.path.append(DIRECTORIO_PADRE)

from aiokafka import AIOKafkaConsumer
from database.oracle_manager import OracleManager

load_dotenv()

# Configuración de logging para salida limpia (solo mensaje)
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

# Clase auxiliar para la configuración de Oracle (requerida por OracleManager)
class OracleConfig:
    def __init__(self):
        self.user = os.getenv("ORACLE__USER")
        self.password = os.getenv("ORACLE__PASSWORD")
        self.dsn = os.getenv("ORACLE__DSN")

async def main():
    # Configuración de timezone
    tz_santiago = pytz.timezone('America/Santiago')

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
    
    # --- Cabecera de la tabla de Ticks ---
    header = f"{'HORA LOCAL':<12} | {'MONEDA':<10} | {'PRECIO':>12} | {'RED (ms)':>10} | {'INT (ms)':>10} | {'ESTADO':<10}"
    separator = "-" * len(header)
    
    logger.info(separator)
    logger.info(header)
    logger.info(separator)

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

            # Transformar now_ms a una hora legible (HH:MM:SS.mmm) en timezone de Santiago
            timestamp_str = datetime.datetime.fromtimestamp(now_ms / 1000.0, tz=tz_santiago).strftime('%H:%M:%S.%f')[:-3]

            # --- 2. Cálculos de latencia ---
            net_latency = now_ms - event_time
            int_latency = now_ms - ingest_time if ingest_time else 0

            # Indicador visual para la tabla
            estado_str = "🔴 CERRADA" if is_closed else "🟢 ABIERTA"

            # Nueva línea de log estandarizada
            log_line = (
                f"{timestamp_str:<12} | "
                f"{f'[{symbol}]':<10} | "
                f"{float(close_price):>12.4f} | "
                f"{net_latency:>10} | "
                f"{int_latency:>10} | "
                f"{estado_str:<10}"
            )
            logger.info(log_line)

            # --- 3. Persistencia en Oracle ---
            if is_closed:
                # Log explícito para ubicar fácilmente la inserción
                logger.info(f"💾 Guardando vela CERRADA en Oracle para {symbol} a las {timestamp_str}")
                
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
                
                loop.run_in_executor(
                    None, 
                    oracle_mgr.insert_candles_batch, 
                    candle_payload
                )
            
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
