-- USING * es seguro acá (y solo acá): ML_TEST_DATA ya es la vista curada
-- por ml_test_data.sql, que solo expone predictor_columns() + el target +
-- identificadores -- no la tabla ancha fct_swing_features. No confundir con
-- fct_trading_signals.sql, que sí necesita la lista explícita porque lee
-- directo de fct_swing_features.
SELECT
    ROUND(AVG(ABS(TARGET_RETURN_72H - PREDICTED_RETURN)), 4) as MAE_72H_ERROR_PCT,
    ROUND(SQRT(AVG(POWER(TARGET_RETURN_72H - PREDICTED_RETURN, 2))), 4) as RMSE_72H_ERROR_PCT
FROM (
    SELECT
        TARGET_RETURN_72H,
        PREDICTION(SWING_XGB_72H_V2 USING *) as PREDICTED_RETURN
    FROM DBT_ANALYTICS.ML_TEST_DATA
    WHERE TARGET_RETURN_72H IS NOT NULL
);