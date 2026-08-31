{{ config(materialized='view') }}

-- Misma lista explícita que ml_train_data.sql (ver
-- transform/macros/feature_set.sql) -- entrenamiento y evaluación tienen
-- que ver exactamente el mismo esquema.
select
    SYMBOL,
    TIMESTAMP_CLT,
    {% for col in predictor_columns() %}
    {{ col }},
    {% endfor %}
    TARGET_RETURN_72H
from {{ ref('fct_swing_features') }}
-- Validamos con los últimos 3 meses (excluyendo hoy)
where TIMESTAMP_CLT >= trunc(sysdate) - 90
-- Horizonte alineado a 72h (ver nota en ml_train_data.sql)
and TARGET_RETURN_72H is not null
