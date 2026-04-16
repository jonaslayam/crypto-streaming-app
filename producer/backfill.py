import asyncio
import logging
import yaml
from pathlib import Path
from datetime import datetime, timedelta
from tqdm import tqdm
import redis.asyncio as redis
from config import Settings

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
        return status if status else None
    
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
        await self.wait_for_rate_limit()
        
        try:
            server_time_res = await self.client.get_server_time()
            binance_now_ms = server_time_res['serverTime']
            
            klines = await self.client.get_historical_klines(
                symbol,
                self.settings.app.timeframe,
                start_str=start_time,
                end_str=end_time,
                limit=BATCH_SIZE
            )
            
            await self.increment_binance_weight(2)
            
            # FIX 1: Si Binance no devuelve NADA (hueco vacío), avanzamos el bloque completo
            if not klines:
                return 0, end_time 
            
            candles_data = []
            
            for k in klines:
                close_time_ms = k[6]
                if close_time_ms < binance_now_ms:
                    candles_data.append((
                        symbol, k[0], 
                        float(k[1]), 
                        float(k[2]), 
                        float(k[3]), 
                        float(k[4]), 
                        float(k[5]), 
                        close_time_ms, 
                        'backfill'       
                    ))
            
            # FIX 2: Llegamos al presente. Solo hay velas abiertas. ¡Adelantar al máximo!
            if not candles_data:
                return 0, binance_now_ms 
            
            loop = asyncio.get_event_loop()
            inserted_count = await loop.run_in_executor(
                None, 
                self.oracle.insert_candles_batch, 
                candles_data
            )
            
            last_timestamp = candles_data[-1][1]
            
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
                time_diff_hours = remaining_ms / (1000 * 3600)
                
                logger.info(
                    f"[{symbol}] Insertadas {inserted} velas | "
                    f"Progreso: {(progress/total_time_ms)*100:.1f}% | "
                    f"Faltan {remaining_days:.1f} días"
                )
                
                # Si no hay velas nuevas y estamos cerca del presente, terminar
                if inserted == 0 and time_diff_hours < READY_THRESHOLD_HOURS:
                    logger.info(f"✅ [{symbol}] Alcanzado el presente (diferencia: {time_diff_hours:.2f}h). Finalizando backfill.")
                    pbar.update(total_time_ms - pbar.n)  # Completar barra
                    await self.set_symbol_status(symbol, 'READY')
                    break
                
                # Avanzar al siguiente batch
                current_time = last_ts + 1
                
                # Pequeña pausa para no saturar
                await asyncio.sleep(0.1)
            
            # Completar barra si no se hizo antes
            pbar.update(total_time_ms - pbar.n)
        
        # Verificar estado final si no se marcó como READY dentro del bucle
        current_status = await self.get_symbol_status(symbol)
        if current_status != 'READY':
            time_diff_hours = (now_ms - current_time) / (1000 * 3600)
            
            if time_diff_hours < READY_THRESHOLD_HOURS:
                await self.set_symbol_status(symbol, 'READY')
                logger.info(f"✅ [{symbol}] Backfill completado. Total insertado: {total_inserted} velas")
            else:
                logger.warning(f"⚠️  [{symbol}] Backfill incompleto. Diferencia: {time_diff_hours:.1f}h")
        else:
            logger.info(f"✅ [{symbol}] Backfill completado. Total insertado: {total_inserted} velas")


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

async def backfill_monitor_loop(client, oracle_manager, initial_settings):
    """
    Bucle perpetuo: Monitor de Integridad y Autodescubrimiento.
    Revisa huecos cada 30 min y detecta nuevos tickers en el YAML.
    """
    logger.info("🕵️ Monitor de Integridad iniciado. Patrullando cada 30 min.")
    base_path = Path(__file__).resolve().parent
    config_path = base_path / "config" / "settings.yaml"

    while True:
        try:
            # 1. Recargar Configuración (Permite "Hot-Reload" de tickers)
            with open(config_path) as f:
                current_cfg = Settings(**yaml.safe_load(f))
            
            logger.info(f"🔍 Iniciando patrulla para {len(current_cfg.binance.tickers)} símbolos...")

            # 2. Conectar a Redis y Oracle para esta vuelta
            redis_client = redis.Redis(host='redis', port=6379, decode_responses=True)
            oracle_manager.connect()

            # 3. Instanciar y procesar
            backfill = SmartDeepBackfill(client, oracle_manager, current_cfg, redis_client)
            
            for symbol in current_cfg.binance.tickers:
                # Si es nuevo, hará el deep backfill de 2 años. 
                # Si ya existe, solo llenará el hueco (ej: los 30 min que durmió).
                await backfill.process_symbol(symbol)

            # 4. Limpieza de sesión
            await redis_client.close()
            oracle_manager.close()
            
            logger.info("✅ Patrulla completada. Base de datos íntegra.")

        except Exception as e:
            logger.error(f"❌ Error en el ciclo del Monitor: {e}")
            # Intentar cerrar conexiones si falló algo
            try: oracle_manager.close()
            except: pass

        # 5. Dormir hasta la próxima ronda
        wait_time = 1800 # 30 minutos
        logger.info(f"😴 Monitor durmiendo por {wait_time/60:.0f} minutos...")
        await asyncio.sleep(wait_time)