{{ config(materialized='view') }}
select * from {{ ref('fct_swing_features') }}
-- Entrenamos con datos hasta hace 3 meses
where TIMESTAMP_CLT < trunc(sysdate) - 90 
and TARGET_RETURN_24H is not null -- Filtramos los nulos del futuro reciente