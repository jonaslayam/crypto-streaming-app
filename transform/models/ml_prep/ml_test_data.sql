{{ config(materialized='view') }}
select * from {{ ref('fct_swing_features') }}
-- Validamos con los últimos 3 meses (excluyendo hoy)
where TIMESTAMP_CLT >= trunc(sysdate) - 90
and TARGET_RETURN_24H is not null