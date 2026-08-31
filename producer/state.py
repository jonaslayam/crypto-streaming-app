import redis.asyncio as redis
import logging
import os

logger = logging.getLogger(__name__)

class RedisState:
    def __init__(self, host: str, port: int = 6379):
        # Usamos un pool para gestionar las conexiones de forma eficiente
        self._redis_pool = redis.ConnectionPool(host=host, port=port, db=0, decode_responses=True)
        self.client = redis.Redis.from_pool(self._redis_pool)

    async def close(self):
        """Cierra la conexión con Redis de forma segura."""
        logger.info("Cerrando conexión con Redis...")
        await self.client.aclose()
        await self._redis_pool.disconnect()
        logger.info("✅ Conexión con Redis cerrada.")

    async def get_last_seen(self, symbol: str) -> int:
        """Obtiene el último timestamp visto para un símbolo."""
        last_seen = await self.client.get(symbol)
        return int(last_seen) if last_seen else 0

    async def update_if_newer(self, symbol: str, event_time: int) -> bool:
        """
        Actualiza el timestamp de un símbolo solo si el nuevo es mayor.
        Utiliza un script LUA para garantizar la atomicidad y evitar race conditions.
        Devuelve True si se actualizó, False en caso contrario.
        """
        # Script LUA para la operación atómica 'compare and set if greater'
        lua_script = """
        local current_val = redis.call('get', KEYS[1])
        if not current_val or tonumber(ARGV[1]) > tonumber(current_val) then
            redis.call('set', KEYS[1], ARGV[1])
            return 1
        else
            return 0
        end
        """
        # El script devuelve 1 si se actualizó, 0 si no
        updated = await self.client.eval(lua_script, 1, symbol, event_time)
        return bool(updated)

# Instancia global para ser usada en toda la aplicación
# El host se determina por la variable de entorno REDIS_HOST.
# - En Docker, será 'redis' (definido en docker-compose.yml).
# - Localmente (WSL), será 'localhost' por defecto.
redis_host = os.getenv("REDIS_HOST", "localhost")
state_manager = RedisState(host=redis_host)
