import json
import logging
from pathlib import Path
from aiokafka import AIOKafkaProducer

logger = logging.getLogger(__name__)

class KafkaProducer:
    def __init__(self, broker: str):
        self.broker = broker
        self.health_file = Path("/tmp/producer_healthy")
        # Creamos la instancia, pero aún no se conecta a la red
        self.producer = AIOKafkaProducer(
            bootstrap_servers=self.broker,
            client_id='crypto-producer',
            # Optimización para 100 monedas: agrupar mensajes mejora el rendimiento
            linger_ms=10 
        )

    async def start(self):
        """Inicia el productor (debe llamarse dentro de un contexto async)"""
        logger.info(f"Conectando el productor a Redpanda en {self.broker}...")
        await self.producer.start()

    async def stop(self):
        """Cierre limpio del productor"""
        logger.info("Cerrando conexión con Redpanda...")
        await self.producer.stop()

    async def send(self, topic: str, key: str, payload: dict):
        """Envía el mensaje de forma asíncrona"""
        try:
            # Serializamos a JSON y enviamos
            value_json = json.dumps(payload).encode("utf-8")
            key_bytes = key.encode("utf-8") if key else None

            # send_and_wait asegura que el mensaje llegó a Redpanda 
            # antes de seguir, manejando el backpressure automáticamente
            await self.producer.send_and_wait(
                topic=topic,
                key=key_bytes,
                value=value_json
            )
            # Actualizamos el fichero de healthcheck tras un envío exitoso
            self.health_file.touch()

        except Exception as e:
            logger.error(f"Error enviando a Kafka: {e}")
            # Re-lanzamos el error para que el worker decida qué hacer (reintentar)
            raise 

    def flush(self):
        # En aiokafka no solemos usar flush manual, 
        # pero mantenemos el nombre por compatibilidad si es necesario
        pass
