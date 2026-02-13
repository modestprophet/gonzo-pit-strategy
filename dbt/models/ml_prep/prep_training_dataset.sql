-- Final training dataset: materialized as table for Keras consumption
-- This is the table that Python training code will read from
-- Note: dbt_ml_preprocessing.one_hot_encoder outputs boolean columns (true/false)
-- Pandas will automatically convert these to 0/1 when loaded

{{ config(materialized='table') }}

SELECT * FROM {{ ref('prep_ohe_driver') }}
