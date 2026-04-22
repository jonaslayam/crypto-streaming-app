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