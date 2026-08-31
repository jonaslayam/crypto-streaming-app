{{ config(materialized='view') }}

-- Lista de columnas explícita (ver transform/macros/feature_set.sql). Antes
-- era "select *", que arrastraba TARGET_RETURN_24H/168H como predictores
-- fantasma (correlacionados con el target real) y precios absolutos no
-- estacionarios entre símbolos. Ver detalle en el macro.
select
    SYMBOL,
    TIMESTAMP_CLT,
    {% for col in predictor_columns() %}
    {{ col }},
    {% endfor %}
    TARGET_RETURN_72H
from {{ ref('fct_swing_features') }}
-- Entrenamos con datos hasta hace 3 meses
where TIMESTAMP_CLT < trunc(sysdate) - 90
-- Horizonte alineado a 72h: el modelo de producción (SWING_XGB_72H_V2)
-- predice a 3 días, no a 1 (antes este filtro decía TARGET_RETURN_24H,
-- un horizonte que ni siquiera es el que se sirve en fct_trading_signals.sql)
and TARGET_RETURN_72H is not null
