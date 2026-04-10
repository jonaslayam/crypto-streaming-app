import asyncio
import logging
from datetime import datetime, timedelta
from state import state_manager

logger = logging.getLogger(__name__)

async def fetch_symbol_backfill(client, producer, settings, symbol):
    # El backfill es dinámico: empieza desde el último punto guardado en Redis.
    last_seen_ts = await state_manager.get_last_seen(symbol)

    now = datetime.now()
    # Límite de seguridad: no pedir más de 15 días de datos históricos.
    max_backfill_limit_ts = int((now - timedelta(days=15)).timestamp() * 1000)

    start_time: int
    if last_seen_ts > 0:
        # Si hay estado, pedimos datos desde el siguiente milisegundo para no repetir.
        start_time = last_seen_ts + 1
        logger.info(f"Resumiendo backfill para {symbol} desde timestamp: {start_time}")
    else:
        # Si no hay estado (primera ejecución), usamos el default de 72h.
        start_time = int((now - timedelta(hours=settings.app.backfill_hours)).timestamp() * 1000)
        logger.info(f"Sin estado previo para {symbol}. Backfill por defecto de {settings.app.backfill_hours}h.")

    # Aplicamos el límite de seguridad
    if start_time < max_backfill_limit_ts:
        logger.warning(f"El punto de inicio del backfill para {symbol} supera los 15 días. Usando el límite.")
        start_time = max_backfill_limit_ts

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
