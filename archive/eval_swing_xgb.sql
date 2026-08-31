-- ARCHIVADO — no ejecutar. Depende de TARGET_RETURN_24H, que ya no existe
-- en ML_TEST_DATA (ver nota en archive/v1_swing_xgb_settings.sql). Evalúa
-- SWING_XGB_24H_V1, superado por SWING_XGB_72H_V2. Se conserva solo como
-- referencia histórica.
--
-- =========================================================================
-- EVALUACIÓN DE RENDIMIENTO: Swing Trading XGBoost V1
-- =========================================================================

SELECT
    ROUND(AVG(ABS(TARGET_RETURN_24H - PREDICTED_RETURN)), 4) as MAE_ERROR_PCT,
    ROUND(SQRT(AVG(POWER(TARGET_RETURN_24H - PREDICTED_RETURN, 2))), 4) as RMSE_ERROR_PCT
FROM (
    SELECT 
        TARGET_RETURN_24H,
        PREDICTION(SWING_XGB_24H_V1 USING *) as PREDICTED_RETURN
    FROM DBT_ANALYTICS.ML_TEST_DATA
    WHERE TARGET_RETURN_24H IS NOT NULL
);