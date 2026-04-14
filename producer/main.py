import asyncio
import logging
import yaml
import os
from pathlib import Path
from binance import AsyncClient

from config import Settings
from producer import KafkaProducer
from ws_client import websocket_loop
from backfill import backfill_monitor_loop
from database.oracle_manager import OracleManager
from state import state_manager

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def queue_to_kafka_worker(queue, producer):
    logger.info("📡 Worker de Kafka iniciado. Esperando eventos live...")
    while True:
        msg = await queue.get()
        try:
            symbol = msg['symbol']
            event_time = msg['event_time']
            payload = msg['payload']
            
            # Solo procesamos si es 'live' para no interferir con el proceso de backfill directo
            await state_manager.update_if_newer(symbol, event_time)
            
            await producer.send(
                topic=msg['topic'],
                key=symbol,
                payload=payload
            )
        except Exception as e:
            logger.error(f"❌ Error enviando a Kafka: {e}")
            await asyncio.sleep(1)
        finally:
            queue.task_done()

async def main():
    # 1. Cargar Configuración
    base_path = Path(__file__).resolve().parent
    config_path = base_path / "config" / "settings.yaml"
    with open(config_path) as f:
        cfg = Settings(**yaml.safe_load(f))

    # 2. Inicializar Infraestructura (Oracle, Kafka, Redis)
    oracle_manager = OracleManager(cfg.oracle)
    
    kafka_broker = os.getenv("KAFKA_BROKER", cfg.kafka.broker)
    producer = KafkaProducer(kafka_broker)
    await producer.start() 

    client = await AsyncClient.create(
        api_key=cfg.binance.api_key,
        api_secret=cfg.binance.api_secret
    )
    
    live_queue = asyncio.Queue(maxsize=10000)

    logger.info("🏗️  Sistemas inicializados. Arrancando motores...")

    try:
        # 3. Lanzar Tareas en Paralelo
        # Tarea A: Backfill Inteligente (Directo a Oracle)
        backfill_task = asyncio.create_task(
            backfill_monitor_loop(client, oracle_manager, cfg)
        )

        # Tarea B: Streaming en Tiempo Real (Hacia Kafka/Redpanda)
        ws_task = asyncio.create_task(
            websocket_loop(client, live_queue, producer, cfg)
        )

        # Tarea C: Worker de vaciado de la cola live
        drain_task = asyncio.create_task(
            queue_to_kafka_worker(live_queue, producer)
        )

        # Mantenemos el programa corriendo mientras las tareas estén vivas
        await asyncio.gather(backfill_task, ws_task, drain_task)

    except Exception as e:
        logger.error(f"💥 Error en el bucle principal: {e}")
    
    finally:
        logger.info("🛑 Iniciando apagado controlado...")
        if 'client' in locals():
            await client.close_connection()
        if 'producer' in locals():
            await producer.stop()
        oracle_manager.close()
        await state_manager.close()
        logger.info("✅ Todos los servicios cerrados.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"FATAL: {e}")