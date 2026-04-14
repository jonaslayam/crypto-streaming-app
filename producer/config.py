from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import BaseModel
from typing import List

class AppConfig(BaseModel):
    update_interval_seconds: int
    timeframe: str
    backfill_days: int
    ready_threshold_hours: int

class KafkaConfig(BaseModel):
    broker: str
    topic: str

class BinanceConfig(BaseModel):
    # Campos obligatorios que no estarán en el YAML, pero sí en el .env
    api_key: str 
    api_secret: str
    tickers: List[str]

class OracleConfig(BaseModel):
    user: str
    password: str
    dsn: str

class Settings(BaseSettings):
    app: AppConfig
    kafka: KafkaConfig
    binance: BinanceConfig
    oracle: OracleConfig  # Añadimos la sección de Oracle
    
    model_config = SettingsConfigDict(
        env_file=".env", 
        env_nested_delimiter="__",
        case_sensitive=False
    )