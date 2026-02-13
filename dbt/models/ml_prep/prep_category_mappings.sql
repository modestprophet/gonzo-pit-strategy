-- Stores distinct category values per categorical column (for inference reuse)
-- This is the "fitted" encoder categories

{{ config(materialized='table') }}

SELECT 'circuit_name' AS feature, circuit_name AS category
FROM (SELECT DISTINCT circuit_name FROM {{ ref('prep_feature_set') }}) sub
UNION ALL
SELECT 'team_name' AS feature, team_name AS category
FROM (SELECT DISTINCT team_name FROM {{ ref('prep_feature_set') }}) sub2
UNION ALL
SELECT 'driver_abbreviation' AS feature, driver_abbreviation AS category
FROM (SELECT DISTINCT driver_abbreviation FROM {{ ref('prep_feature_set') }}) sub3
ORDER BY feature, category
