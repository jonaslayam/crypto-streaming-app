print("--- [DEBUG] El script ha iniciado correctamente ---")
import asyncio
import logging
import yaml
from pathlib import Path
from binance import AsyncClient

from config import Settings
from producer import KafkaProducer
from ws_client import websocket_loop
from backfill import backfill_loop
from state import last_seen
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def queue_to_kafka_worker(queue, producer):
    logger.info("Abriendo la sala de espera hacia Redpanda...")

    while True:
        msg = await queue.get()

        try:
            symbol = msg['symbol']
            event_time = msg['event_time']

            current_limit = last_seen.get(symbol, 0)

            # 🔥 clave: deduplicación + orden lógico
            if event_time <= current_limit:
                continue

            last_seen[symbol] = event_time

            await producer.send(
                topic=msg['topic'],
                key=symbol,
                payload=msg['payload']
            )

        except Exception as e:
            logger.error(f"Error Kafka: {e}, reintentando...")
            await asyncio.sleep(1)
            await queue.put(msg)

        finally:
            queue.task_done()
            
async def main():
    base_path = Path(__file__).resolve().parent
    config_path = base_path / "config" / "settings.yaml"
    with open(config_path) as f:
        cfg = Settings(**yaml.safe_load(f))

    producer = KafkaProducer(cfg.kafka.broker)
    # 🔥 OBLIGATORIO: Encender el productor asíncrono
    await producer.start() 

    client = await AsyncClient.create()
    live_queue = asyncio.Queue(maxsize=10000)

    try:
        ws_task = asyncio.create_task(websocket_loop(client, live_queue, producer, cfg))
        drain_task = asyncio.create_task(queue_to_kafka_worker(live_queue, producer))

        await asyncio.gather(ws_task, drain_task)

    finally:
        print("\n--- [DEBUG] Cerrando servicios de forma segura ---")
        
        # 1. Cerramos Binance (con el nombre correcto)
        if 'client' in locals():
            await client.close_connection()
            print("✅ Conexión con Binance cerrada.")
        
        # 2. Cerramos el Productor de Kafka
        if 'producer' in locals():
            await producer.stop()
            print("✅ Productor de Kafka detenido.")

if __name__ == "__main__":
    print("🚀 Entrando al bloque de ejecución principal...")
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"💥 EL PROGRAMA EXPLOTÓ: {e}")
        import traceback
        traceback.print_exc()