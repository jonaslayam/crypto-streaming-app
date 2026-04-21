import oracledb
import logging

class OracleManager:
    """
    Gestiona la persistencia de datos en Oracle Autonomous Data Warehouse.
    Optimizado para cargas masivas usando un Connection Pool con Auto-Ping.
    """
    def __init__(self, oracle_config):
        self.oracle_config = oracle_config
        self.pool = None
        # Desactivamos el uso de Thick mode para usar conexión TLS simple (Thin)
        oracledb.init_oracle_client = None 
        self._initialize_pool()

    def _initialize_pool(self):
        """Inicializa el Connection Pool con protección contra desconexiones."""
        try:
            self.pool = oracledb.create_pool(
                user=self.oracle_config.user,
                password=self.oracle_config.password,
                dsn=self.oracle_config.dsn,
                min=2,
                max=5,
                increment=1,
                ping_interval=10
            )
            logging.info(f"✅ Oracle Connection Pool inicializado (Mín: 2, Máx: 5).")
        except oracledb.Error as e:
            logging.error(f"❌ Error crítico al crear el Pool de Oracle: {e}")
            raise

    def get_connection(self):
        """Obtiene una conexión sana del Pool."""
        try:
            return self.pool.acquire()
        except oracledb.Error as e:
            logging.error(f"❌ Error al adquirir conexión del pool: {e}")
            raise

    def insert_candles_batch(self, candles_data):
        """
        Inserta un lote de velas en la tabla CRYPTO_CANDLES_1H.
        Usa un Hint de Oracle para ignorar filas que violen la llave primaria.
        """
        if not self.pool:
            self._initialize_pool()

        # SQL con Hint para ignorar duplicados (Idempotencia)
        sql = """
            INSERT /*+ IGNORE_ROW_ON_DUPKEY_INDEX(CRYPTO_CANDLES_1H, PK_CANDLES_1H) */ 
            INTO CRYPTO_CANDLES_1H 
            (SYMBOL, OPEN_TIME_MS, OPEN_PRICE, HIGH_PRICE, LOW_PRICE, CLOSE_PRICE, VOLUME, CLOSE_TIME_MS, SOURCE)
            VALUES (:1, :2, :3, :4, :5, :6, :7, :8, :9)
        """
        
        try:
            # El bloque 'with' asegura que la conexión regrese al pool automáticamente al terminar
            with self.get_connection() as connection:
                with connection.cursor() as cursor:
                    # Ejecución masiva eficiente
                    cursor.executemany(sql, candles_data)
                    inserted_count = cursor.rowcount
                    connection.commit()
                    logging.info(f"💾 Batch insert finalizado. Filas procesadas: {len(candles_data)} (Nuevas: {inserted_count})")
                    return inserted_count
        except oracledb.Error as e:
            logging.error(f"❌ Error durante el batch insert: {e}")
            return 0

    def get_last_timestamp(self, symbol):
        """Obtiene el último timestamp registrado para una moneda específica."""
        sql = "SELECT MAX(OPEN_TIME_MS) FROM CRYPTO_CANDLES_1H WHERE SYMBOL = :1"
        try:
            with self.get_connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(sql, [symbol])
                    result = cursor.fetchone()
                    return result[0] if result and result[0] else None
        except oracledb.Error as e:
            logging.error(f"❌ Error consultando el último timestamp para {symbol}: {e}")
            return None

    def close(self):
        """Cierra el pool completo de forma segura."""
        if self.pool:
            self.pool.close()
            logging.info("🔌 Pool de conexiones a Oracle ADW cerrado.")