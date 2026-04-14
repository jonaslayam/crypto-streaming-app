import asyncio
import logging
from datetime import datetime, timedelta
from tqdm import tqdm
import redis.asyncio as redis

logger = logging.getLogger(__name__)

# Constantes
BACKFILL_DAYS = 730  # 2 años
BATCH_SIZE = 1000
READY_THRESHOLD_HOURS = 1
BINANCE_WEIGHT_LIMIT = 1200
BINANCE_WEIGHT_WINDOW = 60  # segundos


class SmartDeepBackfill:
    """
    Máquina de estados para backfill profundo de datos históricos.
    Estados: LOCKED -> READY
    Persistencia directa en Oracle ADW (sin Kafka).
    """
    
    def __init__(self, client, oracle_manager, settings, redis_client):
        self.client = client
        self.oracle = oracle_manager
        self.settings = settings
        self.redis = redis_client
        
    async def get_binance_weight(self) -> int:
        """Obtiene el peso actual de la API de Binance desde Redis."""
        weight = await self.redis.get('binance:weight')
        return int(weight) if weight else 0
    
    async def increment_binance_weight(self, cost: int = 1):
        """Incrementa el contador de peso de Binance con TTL de 60 segundos."""
        pipe = self.redis.pipeline()
        pipe.incr('binance:weight', cost)
        pipe.expire('binance:weight', BINANCE_WEIGHT_WINDOW)
        await pipe.execute()
    
    async def wait_for_rate_limit(self):
        """Espera si estamos cerca del límite de rate limit de Binance."""
        current_weight = await self.get_binance_weight()
        if current_weight >= BINANCE_WEIGHT_LIMIT:
            wait_time = BINANCE_WEIGHT_WINDOW
            logger.warning(f"⚠️  Rate limit alcanzado ({current_weight}/{BINANCE_WEIGHT_LIMIT}). Esperando {wait_time}s...")
            await asyncio.sleep(wait_time)
    
    async def set_symbol_status(self, symbol: str, status: str):
        """Establece el estado de un símbolo en Redis."""
        await self.redis.set(f'status:{symbol}', status)
        logger.info(f"📊 Estado de {symbol}: {status}")
    
    async def get_symbol_status(self, symbol: str) -> str:
        """Obtiene el estado actual de un símbolo."""
        status = await self.redis.get(f'status:{symbol}')
        return status.decode() if status else None
    
    def determine_start_time(self, symbol: str) -> int:
        """
        Determina el punto de partida para el backfill.
        Prioridad: Oracle DB > 730 días atrás
        """
        last_ts = self.oracle.get_last_timestamp(symbol)
        
        if last_ts:
            logger.info(f"🔄 {symbol}: Continuando desde último timestamp en Oracle: {last_ts}")
            return last_ts + 1  # Siguiente milisegundo
        else:
            start_date = datetime.now() - timedelta(days=BACKFILL_DAYS)
            start_ts = int(start_date.timestamp() * 1000)
            logger.info(f"🆕 {symbol}: Sin datos previos. Iniciando backfill de {BACKFILL_DAYS} días")
            return start_ts
    
    async def fetch_and_store_batch(self, symbol: str, start_time: int, end_time: int) -> tuple[int, int]:
        """
        Descarga un lote de velas y las almacena en Oracle.
        Retorna: (número de velas insertadas, último timestamp procesado)
        """
        await self.wait_for_rate_limit()
        
        try:
            # Petición a Binance (peso: 1)
            klines = await self.client.get_historical_klines(
                symbol,
                self.settings.app.timeframe,
                start_str=start_time,
                end_str=end_time,
                limit=BATCH_SIZE
            )
            
            await self.increment_binance_weight(1)
            
            if not klines:
                return 0, start_time
            
            # Preparar datos para inserción masiva
            # Formato: (SYMBOL, OPEN_TIME_MS, OPEN_PRICE, HIGH_PRICE, LOW_PRICE, CLOSE_PRICE, VOLUME, CLOSE_TIME_MS, SOURCE)
            candles_data = []
            for k in klines:
                candles_data.append((
                    symbol,           # SYMBOL
                    k[0],            # OPEN_TIME_MS
                    float(k[1]),     # OPEN_PRICE
                    float(k[2]),     # HIGH_PRICE
                    float(k[3]),     # LOW_PRICE
                    float(k[4]),     # CLOSE_PRICE
                    float(k[5]),     # VOLUME
                    k[6],            # CLOSE_TIME_MS
                    'backfill'       # SOURCE
                ))
            
            # Inserción masiva en Oracle (idempotente) - ejecutar en executor para no bloquear el loop
            loop = asyncio.get_event_loop()
            inserted_count = await loop.run_in_executor(
                None, 
                self.oracle.insert_candles_batch, 
                candles_data
            )
            
            last_timestamp = klines[-1][0]
            
            return inserted_count, last_timestamp
            
        except Exception as e:
            logger.error(f"❌ Error descargando batch para {symbol}: {e}")
            return 0, start_time
    
    async def process_symbol(self, symbol: str):
        """
        Procesa un símbolo completo con máquina de estados y barra de progreso.
        """
        # Establecer estado inicial
        await self.set_symbol_status(symbol, 'LOCKED')
        
        # Determinar punto de partida
        start_time = self.determine_start_time(symbol)
        now_ms = int(datetime.now().timestamp() * 1000)
        
        # Calcular progreso total
        total_time_ms = now_ms - start_time
        total_hours = total_time_ms / (1000 * 3600)
        
        logger.info(f"🚀 [{symbol}] Iniciando backfill: {total_hours:.1f} horas de datos históricos")
        
        # Barra de progreso
        with tqdm(total=total_time_ms, desc=f"[{symbol}]", unit="ms", unit_scale=True) as pbar:
            current_time = start_time
            total_inserted = 0
            
            while current_time < now_ms:
                # Calcular ventana de tiempo para este batch
                end_time = min(current_time + (BATCH_SIZE * 3600 * 1000), now_ms)
                
                # Descargar y almacenar
                inserted, last_ts = await self.fetch_and_store_batch(symbol, current_time, end_time)
                total_inserted += inserted
                
                # Actualizar progreso
                progress = last_ts - start_time
                pbar.update(progress - pbar.n)
                
                # Calcular tiempo restante
                remaining_ms = now_ms - last_ts
                remaining_days = remaining_ms / (1000 * 3600 * 24)
                
                logger.info(
                    f"[{symbol}] Insertadas {inserted} velas | "
                    f"Progreso: {(progress/total_time_ms)*100:.1f}% | "
                    f"Faltan {remaining_days:.1f} días"
                )
                
                # Avanzar al siguiente batch
                current_time = last_ts + 1
                
                # Pequeña pausa para no saturar
                await asyncio.sleep(0.1)
            
            # Completar barra
            pbar.update(total_time_ms - pbar.n)
        
        # Verificar si llegamos al presente
        time_diff_hours = (now_ms - current_time) / (1000 * 3600)
        
        if time_diff_hours < READY_THRESHOLD_HOURS:
            await self.set_symbol_status(symbol, 'READY')
            logger.info(f"✅ [{symbol}] Backfill completado. Total insertado: {total_inserted} velas")
        else:
            logger.warning(f"⚠️  [{symbol}] Backfill incompleto. Diferencia: {time_diff_hours:.1f}h")


async def smart_deep_backfill(client, oracle_manager, settings):
    """
    Punto de entrada principal para el Smart Deep Backfill.
    Persistencia directa en Oracle ADW (sin Kafka).
    """
    # Conectar a Redis
    redis_client = redis.Redis(host='redis', port=6379, decode_responses=True)
    
    try:
        # Conectar a Oracle
        oracle_manager.connect()
        
        # Crear instancia del backfill
        backfill = SmartDeepBackfill(client, oracle_manager, settings, redis_client)
        
        # Procesar todos los símbolos
        logger.info(f"🎯 Iniciando Smart Deep Backfill para {len(settings.binance.tickers)} símbolos")
        
        for symbol in settings.binance.tickers:
            await backfill.process_symbol(symbol)
        
        logger.info("🎉 Smart Deep Backfill completado para todos los símbolos")
        
    finally:
        await redis_client.close()
        oracle_manager.close()
