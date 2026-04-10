import asyncio
import json
import logging
import os
import time
from aiokafka import AIOKafkaConsumer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    KAFKA_BROKER = os.getenv("KAFKA_BROKER", "localhost:19092")
    TOPIC_NAME = "crypto-raw"
    GROUP_ID = "crypto-analytics-v1"

    consumer = AIOKafkaConsumer(
        TOPIC_NAME,
        bootstrap_servers=KAFKA_BROKER,
        group_id=GROUP_ID,
        auto_offset_reset='earliest',
        value_deserializer=lambda m: json.loads(m.decode('utf-8'))
    )

    logger.info("Iniciando consumidor...")
    await consumer.start()
    logger.info(f"Consumidor conectado. Escuchando topic '{TOPIC_NAME}' con group_id '{GROUP_ID}'.")

    try:
        async for msg in consumer:
            now_ms = int(time.time() * 1000)
            data = msg.value
            
            ingest_time = data.get('ingest_time')
            if ingest_time is None:
                logger.warning("Mensaje recibido sin 'ingest_time'. Omitiendo cálculo de latencia.")
                continue

            latency_ms = now_ms - ingest_time
            symbol = data.get('symbol', 'N/A')
            close_price = data.get('close', 'N/A')
            partition = msg.partition

            print(f"[PARTITION {partition}] {symbol} | Precio: {close_price} | Latencia Total: {latency_ms}ms.")
            
    finally:
        logger.info("Cerrando consumidor...")
        await consumer.stop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Proceso interrumpido por el usuario.")
    except Exception as e:
        logger.error(f"Error inesperado en el consumidor: {e}")
        import traceback
        traceback.print_exc()
