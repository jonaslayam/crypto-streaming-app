import asyncio
import logging
from binance import BinanceSocketManager

logger = logging.getLogger(__name__)

async def websocket_loop(client, queue, producer, settings):
    bm = BinanceSocketManager(client)

    # Convertimos los tickers a minúsculas para el stream de Binance
    streams = [f"{s.lower()}@kline_{settings.app.timeframe}" for s in settings.binance.tickers]

    while True:
        try:
            logger.info("📡 Conectando WebSocket de Binance...")
            
            # 🛑 ELIMINAMOS: asyncio.create_task(backfill_loop(...))
            # El backfill ahora lo gestiona el main.py de forma independiente.
            
            async with bm.multiplex_socket(streams) as stream:
                while True:
                    msg = await stream.recv()

                    if not msg or 'data' not in msg:
                        continue

                    data = msg['data']
                    
                    if 'E' not in data:
                        continue

                    k = data.get('k')
                    if not k:
                        continue

                    symbol = data['s']
                    event_time = data['E'] 

                    payload = {
                        'symbol': symbol,
                        'event_time': event_time,
                        'kline_open_time': k['t'],
                        'kline_close_time': k['T'],
                        'open': k['o'],
                        'high': k['h'],
                        'low': k['l'],
                        'close': k['c'],
                        'volume': k['v'],
                        'is_closed': k['x'],
                        'source': 'live'
                    }

                    # Enviar a la cola interna para el worker de Kafka
                    await queue.put({
                        'topic': settings.kafka.topic,
                        'symbol': symbol,
                        'event_time': k['t'],
                        'payload': payload
                    })

        except Exception as e:
            logger.warning(f"⚠️ WS error: {e} → reintentando en 5s...")
            await asyncio.sleep(5)