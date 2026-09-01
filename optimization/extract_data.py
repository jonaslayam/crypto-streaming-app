import sys
import os
import warnings

# 1. Silenciamos advertencias
warnings.filterwarnings('ignore', category=UserWarning)

# 2. Forzamos timezone numérico en la sesión
os.environ['ORA_SDTZ'] = '-04:00'

DIRECTORIO_ACTUAL = os.path.dirname(os.path.abspath(__file__))
DIRECTORIO_PADRE = os.path.dirname(DIRECTORIO_ACTUAL)
sys.path.append(DIRECTORIO_PADRE)

import pandas as pd
import logging
from database.oracle_manager import OracleManager
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv(os.path.join(DIRECTORIO_PADRE, '.env'))

class OracleConfig:
    def __init__(self):
        self.user = os.getenv("ORACLE__USER")
        self.password = os.getenv("ORACLE__PASSWORD")
        self.dsn = os.getenv("ORACLE__DSN")


def get_columns(cursor):
    """
    Obtiene todas las columnas de la tabla excepto TIMESTAMP_CLT
    """
    cursor.execute("""
        SELECT column_name
        FROM all_tab_columns
        WHERE table_name = 'FCT_SWING_FEATURES'
        AND owner = 'DBT_ANALYTICS'
        ORDER BY column_id
    """)
    
    cols = [row[0] for row in cursor.fetchall()]
    
    # Excluimos la columna problemática
    cols = [c for c in cols if c != 'TIMESTAMP_CLT']
    
    return cols


def build_query(columns):
    """
    Construye el SELECT dinámico evitando duplicados
    """
    return f"""
    SELECT 
        TO_CHAR(TIMESTAMP_CLT AT TIME ZONE '-04:00', 'YYYY-MM-DD HH24:MI:SS') AS TIMESTAMP_CLT,
        {', '.join(columns)}
    FROM DBT_ANALYTICS.FCT_SWING_FEATURES
    ORDER BY TIMESTAMP_CLT ASC
    """


def extract():
    logging.basicConfig(level=logging.INFO)
    config = OracleConfig()
    
    if not config.dsn:
        logging.error("❌ Faltan credenciales en el .env")
        return
        
    db = OracleManager(config)
    
    try:
        logging.info("📥 Conectando a Oracle...")
        
        with db.get_connection() as conn:
            with conn.cursor() as cursor:
                
                # 🔥 Obtener columnas dinámicamente
                columns = get_columns(cursor)
                
                # 🔥 Construir query segura
                query = build_query(columns)
                
                logging.info("📥 Ejecutando query con fix de timezone...")
                cursor.execute(query)
                
                column_names = [col[0] for col in cursor.description]
                rows = cursor.fetchall()
            
            df = pd.DataFrame(rows, columns=column_names)

        # 🔥 Convertir a datetime en pandas (opcional pero recomendado)
        df['TIMESTAMP_CLT'] = pd.to_datetime(df['TIMESTAMP_CLT'])

        # Guardar CSV
        output_path = os.path.join(DIRECTORIO_PADRE, "optimization", "data", "crypto_history.csv")
        df.to_csv(output_path, index=False)
        
        logging.info(f"✅ Extracción completada: {len(df)} filas descargadas.")
        logging.info(f"📁 Archivo guardado en: {output_path}")
        
    except Exception as e:
        logging.error(f"❌ Error en la extracción: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    extract()