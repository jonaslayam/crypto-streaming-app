{% macro predictor_columns() %}
{#
    Lista canónica de columnas predictoras del modelo de swing trading.

    Se invoca desde AMBOS lados de la frontera de entrenamiento/inferencia:
    ml_prep/ml_train_data.sql y ml_prep/ml_test_data.sql (para curar la
    tabla con la que se entrena y evalúa el modelo OML) y desde
    marts/fct_trading_signals.sql (para el PREDICTION(...) USING (...) en
    producción). Antes cada lado tenía su propia lista implícita —
    "select *" en un lado, "USING *" en el otro— y podían divergir sin que
    nada lo detectara. Esa divergencia es el train/serve skew documentado
    en la auditoría: en la vela viva, las columnas que "select *" arrastraba
    desde fct_swing_features (los propios TARGET_RETURN_*) llegan en NULL,
    y el modelo terminaba prediciendo con features que en entrenamiento
    jamás fueron NULL.

    Deliberadamente EXCLUIDOS de esta lista:
      - TARGET_RETURN_24H / TARGET_RETURN_72H / TARGET_RETURN_168H
        (salvo el target real de entrenamiento, que se agrega aparte en
        ml_train_data.sql / ml_test_data.sql). Los otros horizontes están
        correlacionados con el target (corr 72h-24h = 0.576, corr
        72h-168h = 0.645 según la auditoría) y colándose como predictor
        vía "select *" inflaban el R² de forma artificial.
      - CLOSE_PRICE, VOLUME, SMA_20/50/200/720, ATR_14, BB_UPPER_20,
        BB_LOWER_20, STDDEV_20, MAX_PRICE_48H, MIN_PRICE_48H: niveles
        absolutos de precio/volumen, no estacionarios al entrenar un
        único modelo pooled sobre BTC (~$62.000) y ADA (~$0.45) a la vez.
        (CLOSE_PRICE, ATR_14 y SMA_200 se siguen usando tal cual, fuera
        del modelo, en la lógica de reglas de fct_trading_signals.sql —
        ahí sí es válido porque compara cada fila contra sí misma, no
        agrupa entre símbolos.)

    Solo quedan columnas ya normalizadas o acotadas: RSI (0-100),
    z-scores, un ratio de posición 0-1 y volumen relativo.
#}
{%- set cols = [
    'RSI_14',
    'RSI_24',
    'Z_SCORE_20',
    'Z_SCORE_24',
    'RANGE_POS_48H',
    'RVOL_20'
] -%}
{{ return(cols) }}
{% endmacro %}
