-- Select only training-relevant columns, drop IDs/dates/raw strings
-- Replaces DropColumns (step 11)

SELECT
    -- Categorical (to be encoded)
    circuit_name,
    team_name,
    driver_abbreviation,
    
    -- Numeric (to be scaled)
    qualifying_position,
    grid,
    points,
    driver_championship_points,
    team_championship_points,
    driver_championship_position,
    driver_wins,
    team_championship_position,
    team_wins,
    q1_seconds,
    q2_seconds,
    q3_seconds,
    race_time_ms_clipped AS race_time_ms,
    prev_race_points,
    prev_race_driver_championship_points,
    prev_race_driver_championship_position,
    prev_race_driver_wins,
    prev_race_team_championship_points,
    prev_race_team_championship_position,
    prev_race_team_wins,
    prev_race_race_time_ms,
    
    -- Already numeric, no scaling needed
    q1_time_missing,
    q2_time_missing,
    q3_time_missing,
    is_dnf,
    season_progress_percent,
    
    -- Target
    finish_position
FROM {{ ref('feat_clipped') }}
