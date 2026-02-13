-- Stores mean/stddev for each scaled column (for inference reuse)
-- This is the "fitted" scaler parameters

{{ config(materialized='table') }}

{% set numeric_cols = [
    'qualifying_position', 'grid', 'points',
    'driver_championship_points', 'team_championship_points',
    'driver_championship_position', 'driver_wins',
    'team_championship_position', 'team_wins',
    'q1_seconds', 'q2_seconds', 'q3_seconds', 'race_time_ms',
    'prev_race_points', 'prev_race_driver_championship_points',
    'prev_race_driver_championship_position', 'prev_race_driver_wins',
    'prev_race_team_championship_points', 'prev_race_team_championship_position',
    'prev_race_team_wins', 'prev_race_race_time_ms'
] %}

{% for col in numeric_cols %}
SELECT
    '{{ col }}' AS column_name,
    AVG({{ col }})::float AS mean_val,
    STDDEV_POP({{ col }})::float AS stddev_val
FROM {{ ref('prep_feature_set') }}
{% if not loop.last %}UNION ALL{% endif %}
{% endfor %}
