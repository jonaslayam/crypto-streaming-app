import oracledb
import logging

class OracleManager:
    """
    Gestiona la persistencia de datos en Oracle Autonomous Data Warehouse.
    Optimizado para cargas masivas y conexión TLS sin Wallet.
    """
    def __init__(self, config):
        self.config = config
        self.connection = None
        # Desactivamos el uso de Thick mode para usar conexión TLS simple (Thin)
        oracledb.init_oracle_client = None 

    def connect(self):
        """Establece la conexión con ADW usando los parámetros de configuración."""
        try:
            self.connection = oracledb.connect(
                user=self.config.DB_USER,
                password=self.config.DB_PASSWORD,
                dsn=self.config.DB_DSN
            )
            logging.info(f"✅ Conexión establecida con Oracle ADW (Usuario: {self.config.DB_USER})")
        except oracledb.Error as e:
            logging.error(f"❌ Error crítico al conectar con Oracle: {e}")
            raise

    def insert_candles_batch(self, candles_data):
        """
        Inserta un lote de velas en la tabla CRYPTO_CANDLES_1H.
        Usa un Hint de Oracle para ignorar filas que violen la llave primaria.
        """
        if not self.connection:
            self.connect()

        # SQL con Hint para ignorar duplicados (Idempotencia)
        sql = """
            INSERT /*+ IGNORE_ROW_ON_DUPKEY_INDEX(CRYPTO_CANDLES_1H, PK_CANDLES_1H) */ 
            INTO CRYPTO_CANDLES_1H 
            (SYMBOL, OPEN_TIME_MS, OPEN_PRICE, HIGH_PRICE, LOW_PRICE, CLOSE_PRICE, VOLUME, CLOSE_TIME_MS, SOURCE)
            VALUES (:1, :2, :3, :4, :5, :6, :7, :8, :9)
        """
        
        try:
            with self.connection.cursor() as cursor:
                # Ejecución masiva eficiente
                cursor.executemany(sql, candles_data)
                inserted_count = cursor.rowcount
                self.connection.commit()
                logging.info(f"💾 Batch insert finalizado. Filas procesadas: {len(candles_data)} (Nuevas: {inserted_count})")
                return inserted_count
        except oracledb.Error as e:
            self.connection.rollback()
            logging.error(f"❌ Error durante el batch insert: {e}")
            return 0

    def get_last_timestamp(self, symbol):
        """Obtiene el último timestamp registrado para una moneda específica."""
        sql = "SELECT MAX(OPEN_TIME_MS) FROM CRYPTO_CANDLES_1H WHERE SYMBOL = :1"
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(sql, [symbol])
                result = cursor.fetchone()
                return result[0] if result and result[0] else None
        except oracledb.Error as e:
            logging.error(f"❌ Error consultando el último timestamp para {symbol}: {e}")
            return None

    def close(self):
        """Cierra la conexión de forma segura."""
        if self.connection:
            self.connection.close()
            logging.info("🔌 Conexión con Oracle ADW cerrada.")