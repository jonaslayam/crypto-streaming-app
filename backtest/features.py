"""Lista de columnas predictoras.

Debe coincidir exactamente con predictor_columns() en
transform/macros/feature_set.sql -- ese macro es la fuente de verdad para
lo que el modelo de producción usa como features; esta lista es su espejo
en Python para que el backtest evalúe la misma información que el modelo
real, ni más ni menos. Si una diverge de la otra, este backtest deja de
medir la estrategia real.

Deliberadamente EXCLUIDOS (ver el macro de dbt para el detalle completo):
TARGET_RETURN_* salvo el target de entrenamiento, y los niveles absolutos
de precio/volumen (CLOSE_PRICE, VOLUME, SMA_*, ATR_14, BB_*, STDDEV_20,
MAX_PRICE_48H, MIN_PRICE_48H) -- no estacionarios entre símbolos.
"""

PREDICTOR_COLUMNS = [
    "RSI_14",
    "RSI_24",
    "Z_SCORE_20",
    "Z_SCORE_24",
    "RANGE_POS_48H",
    "RVOL_20",
]

# Columnas que el motor de ejecución sí necesita fuera del modelo (precio y
# ATR para el stop-loss). No se le pasan al modelo como predictores.
EXECUTION_COLUMNS = ["CLOSE_PRICE", "ATR_14"]

TARGET_COLUMN_TEMPLATE = "TARGET_RETURN_{h}H"


def target_column(horizon_hours: int) -> str:
    return TARGET_COLUMN_TEMPLATE.format(h=horizon_hours)
