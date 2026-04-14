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
    GROUP_ID = "crypto-analytics-v2"

    consumer = AIOKafkaConsumer(
        TOPIC_NAME,
        bootstrap_servers=KAFKA_BROKER,
        group_id="test-latency-" + str(time.time()),
        auto_offset_reset='latest',
        value_deserializer=lambda m: json.loads(m.decode('utf-8'))
    )

    logger.info("🚀 Iniciando consumidor de baja latencia...")
    await consumer.start()
    logger.info(f"✅ Conectado a {TOPIC_NAME}. Monitoreando latencia de red...")

    try:
        async for msg in consumer:
            # Timestamp actual en UTC ms
            now_ms = int(time.time() * 1000)
            data = msg.value
            
            # 1. Extraemos el tiempo del evento (Binance 'E')
            event_time = data.get('event_time')
            # 2. Extraemos el tiempo de ingesta (Tu Producer)
            ingest_time = data.get('ingest_time')

            if not event_time:
                logger.warning("Mensaje sin 'event_time'.")
                continue

            # Latencia de Red + Pipeline (Desde Binance hasta aquí)
            total_latency = now_ms - event_time
            
            # Latencia Interna (Solo desde tu Producer hasta aquí)
            # Útil para saber si el cuello de botella es tu internet o tu código
            internal_latency = now_ms - ingest_time if ingest_time else 0

            symbol = data.get('symbol', 'N/A')
            close_price = data.get('close', 'N/A')
            
            # Formateo limpio para monitoreo
            print(f"[{symbol}] P: {close_price} | 🛰️ Latencia Red: {total_latency}ms | ⚙️ Latencia Interna: {internal_latency}ms")
            
    finally:
        logger.info("🔌 Cerrando consumidor...")
        await consumer.stop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass