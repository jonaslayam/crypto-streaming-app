import asyncio
import logging
import os
from aiokafka.admin import AIOKafkaAdminClient, NewTopic
from aiokafka.errors import TopicAlreadyExistsError, KafkaConnectionError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def setup_topic():
    KAFKA_BROKER = os.getenv("KAFKA_BROKER", "localhost:19092")
    TOPIC_NAME = "crypto-raw"
    PARTITIONS = 4
    REPLICATION_FACTOR = 1
    
    admin_client = None
    retries = 10
    for i in range(retries):
        try:
            logger.info(f"Attempting to connect to Kafka ({i+1}/{retries})...")
            admin_client = AIOKafkaAdminClient(bootstrap_servers=KAFKA_BROKER)
            await admin_client.start()
            logger.info("✅ Connection to Kafka successful.")
            break
        except KafkaConnectionError as e:
            logger.warning(f"Failed to connect to Kafka: {e}. Retrying in 5 seconds...")
            await asyncio.sleep(5)
            if i == retries - 1:
                logger.error("Could not connect to Kafka after multiple retries.")
                exit(1)
    
    if not admin_client:
        logger.error("Admin client not initialized.")
        exit(1)

    try:
        logger.info(f"Attempting to create topic '{TOPIC_NAME}' with {PARTITIONS} partitions...")
        topic_list = [
            NewTopic(
                name=TOPIC_NAME,
                num_partitions=PARTITIONS,
                replication_factor=REPLICATION_FACTOR
            )
        ]
        await admin_client.create_topics(topic_list)
        logger.info(f"✅ Topic '{TOPIC_NAME}' created successfully.")
    except TopicAlreadyExistsError:
        logger.info(f"➡️  Topic '{TOPIC_NAME}' already exists. No action taken.")
    except Exception as e:
        logger.error(f"❌ An error occurred while creating topic: {e}")
        exit(1)
    finally:
        await admin_client.close()

if __name__ == "__main__":
    asyncio.run(setup_topic())
