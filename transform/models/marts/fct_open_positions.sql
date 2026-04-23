-- models/marts/fct_open_positions.sql
{{ config(materialized='view') }}

with signals as (
    select * from {{ ref('fct_trading_signals') }}
),
closed_trades as (
    -- Esta tabla la alimenta Flink simulando el Exchange
    select symbol, entry_time from {{ source('exchange_api', 'raw_executed_trades') }}
    where action = 'SELL'
),
open_trades as (
    select 
        s.SYMBOL,
        s.TIMESTAMP_CLT as entry_time,
        s.CLOSE_PRICE as entry_price,     -- AQUÍ DEVOLVEMOS EL NOMBRE CORRECTO
        s.SIGNAL as entry_type,
        s.SUGGESTED_STOP_LOSS as initial_stop
    from signals s
    left join closed_trades c 
      on s.symbol = c.symbol and s.timestamp_clt = c.entry_time
    where s.signal in ('STEADY_GROWTH', 'VOLATILE_REVERSAL')
      and c.symbol is null -- CRÍTICO: Excluimos los que ya se vendieron
)
select * from open_trades