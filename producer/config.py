from pydantic import BaseModel

class KafkaConfig(BaseModel):
    broker: str
    topic: str

class BinanceConfig(BaseModel):
    tickers: list[str]

class AppConfig(BaseModel):
    update_interval_seconds: int = 2
    timeframe: str = "1h"
    backfill_hours: int = 72

class Settings(BaseModel):
    app: AppConfig
    kafka: KafkaConfig
    binance: BinanceConfig