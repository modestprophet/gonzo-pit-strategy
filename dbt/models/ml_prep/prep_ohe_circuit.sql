-- One-hot encode circuit_name (step 1 of 3)
-- Custom implementation to handle special characters in names
-- Replaces CategoricalEncoder (step 5) for circuit_name

{% set circuits_query %}
    SELECT DISTINCT circuit_name 
    FROM {{ ref('prep_scaled') }}
    ORDER BY circuit_name
{% endset %}

{% set results = run_query(circuits_query) %}
{% if execute %}
    {% set circuits = results.columns[0].values() %}
{% else %}
    {% set circuits = [] %}
{% endif %}

SELECT
    -- Pass through all non-categorical columns
    team_name,
    driver_abbreviation,
    q1_time_missing,
    q2_time_missing,
    q3_time_missing,
    is_dnf,
    season_progress_percent,
    finish_position,
    qualifying_position_scaled,
    grid_scaled,
    points_scaled,
    driver_championship_points_scaled,
    team_championship_points_scaled,
    driver_championship_position_scaled,
    driver_wins_scaled,
    team_championship_position_scaled,
    team_wins_scaled,
    q1_seconds_scaled,
    q2_seconds_scaled,
    q3_seconds_scaled,
    race_time_ms_scaled,
    prev_race_points_scaled,
    prev_race_driver_championship_points_scaled,
    prev_race_driver_championship_position_scaled,
    prev_race_driver_wins_scaled,
    prev_race_team_championship_points_scaled,
    prev_race_team_championship_position_scaled,
    prev_race_team_wins_scaled,
    prev_race_race_time_ms_scaled,
    
    -- One-hot encoded circuit columns
    {% for circuit in circuits %}
    CASE WHEN circuit_name = '{{ circuit }}' THEN 1 ELSE 0 END AS circuit_{{ clean_column_name(circuit) }}
    {% if not loop.last %},{% endif %}
    {% endfor %}
FROM {{ ref('prep_scaled') }}
