import asyncio
import logging
from binance import BinanceSocketManager
from state import last_seen
from backfill import backfill_loop

logger = logging.getLogger(__name__)

async def websocket_loop(client, queue, producer, settings):
    bm = BinanceSocketManager(client)

    # Convertimos los tickers a minúsculas para el stream de Binance
    streams = [f"{s.lower()}@kline_{settings.app.timeframe}" for s in settings.binance.tickers]

    while True:
        try:
            logger.info("📡 Conectando WebSocket...")
            
            # 🔥 Lanzamos el backfill en paralelo
            asyncio.create_task(backfill_loop(client, producer, settings))
            
            async with bm.multiplex_socket(streams) as stream:
                while True:
                    msg = await stream.recv()

                    # 1. Seguridad: Si el mensaje no tiene 'data', es un saludo o error de Binance
                    if not msg or 'data' not in msg:
                        continue

                    data = msg['data']
                    
                    # 2. Seguridad: Si no hay 'E', es un mensaje de sistema, lo ignoramos
                    if 'E' not in data:
                        continue

                    # 3. Extraemos 'k' (los datos de la vela)
                    k = data.get('k')
                    if not k:
                        continue

                    # --- EXTRACCIÓN CORRECTA ---
                    symbol = data['s']
                    event_time = data['E']  # ✅ 'E' vive en data, no en k

                    # Armamos el payload con el que trabajará Flink después
                    payload = {
                        'symbol': symbol,
                        'event_time': event_time,
                        'kline_close_time': k['T'],
                        'open': k['o'],
                        'high': k['h'],
                        'low': k['l'],
                        'close': k['c'],
                        'volume': k['v'],
                        'is_closed': k['x']
                    }

                    # Metemos a la cola para que el worker lo envíe a Redpanda
                    await queue.put({
                        'topic': settings.kafka.topic,
                        'symbol': symbol,
                        'event_time': event_time,
                        'payload': payload
                    })

        except Exception as e:
            logger.warning(f"WS error: {e} → retrying in 5s...")
            await asyncio.sleep(5)