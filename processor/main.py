import asyncio
import json
import logging
import os
import time
from aiokafka import AIOKafkaConsumer

# Configuración de logging básica
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def main():
    KAFKA_BROKER = os.getenv("KAFKA_BROKER", "localhost:19092")
    TOPIC_NAME = "crypto-raw"
    
    # Usamos un ID de grupo dinámico para asegurar que leemos desde el 'latest' en cada reinicio
    GROUP_ID = f"latency-monitor-{int(time.time())}"

    consumer = AIOKafkaConsumer(
        TOPIC_NAME,
        bootstrap_servers=KAFKA_BROKER,
        group_id=GROUP_ID,
        auto_offset_reset='latest',
        value_deserializer=lambda m: json.loads(m.decode('utf-8'))
    )

    logger.info("🚀 Iniciando monitor de latencia en tiempo real...")
    await consumer.start()
    
    # Definición de la cabecera para las columnas
    # <12: Alineado a la izquierda, 12 espacios
    # >15: Alineado a la derecha, 15 espacios
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
            
            event_time = data.get('event_time')
            ingest_time = data.get('ingest_time')
            symbol = data.get('symbol', 'N/A')
            close_price = data.get('close', 0.0)

            if not event_time:
                continue

            # Cálculos de latencia
            net_latency = now_ms - event_time
            int_latency = now_ms - ingest_time if ingest_time else 0

            # Formateo de la línea de datos
            # :>15.4f -> 15 espacios, 4 decimales fijos
            log_line = (
                f"{f'[{symbol}]':<12} | "
                f"{float(close_price):>15.4f} | "
                f"{net_latency:>12} | "
                f"{int_latency:>10}"
            )

            print(log_line)
            
            # Repetir cabecera cada 20 mensajes para legibilidad
            msg_count += 1
            if msg_count % 20 == 0:
                print(separator)
                print(header)
                print(separator)
            
    except Exception as e:
        logger.error(f"❌ Error en el consumidor: {e}")
    finally:
        logger.info("🔌 Cerrando conexión...")
        await consumer.stop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Monitor detenido por el usuario.")