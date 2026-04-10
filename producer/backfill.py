import asyncio
import logging
from datetime import datetime, timedelta
from state import state_manager

logger = logging.getLogger(__name__)

async def fetch_symbol_backfill(client, producer, settings, symbol):
    start_time = int((datetime.now() - timedelta(hours=settings.app.backfill_hours)).timestamp() * 1000)

    try:
        klines = await client.get_historical_klines(
            symbol,
            settings.app.timeframe,
            start_str=start_time
        )

        for k in klines:
            event_time = k[0]

            # Operación atómica: solo si el evento es más nuevo se actualiza y se envía
            was_updated = await state_manager.update_if_newer(symbol, event_time)
            if not was_updated:
                logger.debug(f"Vela {symbol} [{event_time}] ya existe en Redis, omitiendo...")
                continue

            payload = {
                'symbol': symbol,
                'event_time': event_time,
                'kline_open_time': event_time,
                'kline_close_time': k[6],
                'open': k[1],
                'high': k[2],
                'low': k[3],
                'close': k[4],
                'volume': k[5],
                'is_closed': True,
                'source': 'backfill'
            }

            await producer.send(settings.kafka.topic, symbol, payload)

        logger.info(f"Backfill OK {symbol} ({len(klines)} velas)")

    except Exception as e:
        logger.error(f"Backfill error {symbol}: {e}")


async def backfill_loop(client, producer, settings):
    tasks = [
        fetch_symbol_backfill(client, producer, settings, s)
        for s in settings.binance.tickers
    ]

    await asyncio.gather(*tasks)
