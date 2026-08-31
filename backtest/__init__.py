"""Arnés de validación honesto para la estrategia de swing trading.

Reemplaza a optimization/optimize_swing.py (ver archive/optimize_swing.py
para el detalle de por qué ese script no sirve: lookahead bias real en
`pred_72h`, y un bug de posiciones huérfanas que descartaba silenciosamente
el 99% de las salidas). Este paquete existe para que un resultado positivo
o negativo se pueda confiar, no para que la estrategia "gane" el backtest.

Uso:
    python -m backtest --dry-run
    python -m backtest --report
"""
