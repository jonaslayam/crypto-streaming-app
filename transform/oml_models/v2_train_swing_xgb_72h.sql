-- =========================================================================
-- MODELO: Swing Trading XGBoost V2 (Target: 72 Horas / 3 Días)
-- =========================================================================

-- 1. CONFIGURACIÓN (Ajustamos un poco para mayor alcance)
BEGIN
   EXECUTE IMMEDIATE 'DROP TABLE DBT_ANALYTICS.ML_XGB_SETTINGS_72H';
EXCEPTION
   WHEN OTHERS THEN NULL;
END;
/

CREATE TABLE DBT_ANALYTICS.ML_XGB_SETTINGS_72H (
    setting_name  VARCHAR2(30),
    setting_value VARCHAR2(4000)
);

INSERT INTO DBT_ANALYTICS.ML_XGB_SETTINGS_72H VALUES ('ALGO_NAME', 'ALGO_XGBOOST');
INSERT INTO DBT_ANALYTICS.ML_XGB_SETTINGS_72H VALUES ('PREP_AUTO', 'ON');
INSERT INTO DBT_ANALYTICS.ML_XGB_SETTINGS_72H VALUES ('booster', 'gbtree');
INSERT INTO DBT_ANALYTICS.ML_XGB_SETTINGS_72H VALUES ('max_depth', '6'); -- Aumentamos de 5 a 6 para captar patrones de 3 días
INSERT INTO DBT_ANALYTICS.ML_XGB_SETTINGS_72H VALUES ('eta', '0.05');   -- Bajamos el learning rate para que sea más preciso
COMMIT;
/

-- 2. ENTRENAMIENTO
BEGIN
    BEGIN DBMS_DATA_MINING.DROP_MODEL('SWING_XGB_72H_V2'); EXCEPTION WHEN OTHERS THEN NULL; END;

    DBMS_DATA_MINING.CREATE_MODEL(
        model_name          => 'SWING_XGB_72H_V2',
        mining_function     => DBMS_DATA_MINING.REGRESSION,
        data_table_name     => 'DBT_ANALYTICS.ML_TRAIN_DATA',
        case_id_column_name => 'TIMESTAMP_CLT',
        target_column_name  => 'TARGET_RETURN_72H', -- <--- CAMBIO CLAVE: Ahora miramos a 3 días
        settings_table_name => 'DBT_ANALYTICS.ML_XGB_SETTINGS_72H'
    );
END;
/