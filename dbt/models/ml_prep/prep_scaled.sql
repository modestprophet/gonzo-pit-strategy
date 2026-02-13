-- Apply StandardScaler to numeric columns
-- Replaces NumericalScaler (step 6)
-- Using inline SQL with NULLIF to handle zero stddev

SELECT
    -- Pass through columns
    circuit_name,
    team_name,
    driver_abbreviation,
    q1_time_missing,
    q2_time_missing,
    q3_time_missing,
    is_dnf,
    season_progress_percent,
    finish_position,
    
    -- Scaled columns with NULLIF protection
    (qualifying_position - AVG(qualifying_position) OVER()) / NULLIF(STDDEV_POP(qualifying_position) OVER(), 0) AS qualifying_position_scaled,
    (grid - AVG(grid) OVER()) / NULLIF(STDDEV_POP(grid) OVER(), 0) AS grid_scaled,
    (points - AVG(points) OVER()) / NULLIF(STDDEV_POP(points) OVER(), 0) AS points_scaled,
    (driver_championship_points - AVG(driver_championship_points) OVER()) / NULLIF(STDDEV_POP(driver_championship_points) OVER(), 0) AS driver_championship_points_scaled,
    (team_championship_points - AVG(team_championship_points) OVER()) / NULLIF(STDDEV_POP(team_championship_points) OVER(), 0) AS team_championship_points_scaled,
    (driver_championship_position - AVG(driver_championship_position) OVER()) / NULLIF(STDDEV_POP(driver_championship_position) OVER(), 0) AS driver_championship_position_scaled,
    (driver_wins - AVG(driver_wins) OVER()) / NULLIF(STDDEV_POP(driver_wins) OVER(), 0) AS driver_wins_scaled,
    (team_championship_position - AVG(team_championship_position) OVER()) / NULLIF(STDDEV_POP(team_championship_position) OVER(), 0) AS team_championship_position_scaled,
    (team_wins - AVG(team_wins) OVER()) / NULLIF(STDDEV_POP(team_wins) OVER(), 0) AS team_wins_scaled,
    (q1_seconds - AVG(q1_seconds) OVER()) / NULLIF(STDDEV_POP(q1_seconds) OVER(), 0) AS q1_seconds_scaled,
    (q2_seconds - AVG(q2_seconds) OVER()) / NULLIF(STDDEV_POP(q2_seconds) OVER(), 0) AS q2_seconds_scaled,
    (q3_seconds - AVG(q3_seconds) OVER()) / NULLIF(STDDEV_POP(q3_seconds) OVER(), 0) AS q3_seconds_scaled,
    (race_time_ms - AVG(race_time_ms) OVER()) / NULLIF(STDDEV_POP(race_time_ms) OVER(), 0) AS race_time_ms_scaled,
    (prev_race_points - AVG(prev_race_points) OVER()) / NULLIF(STDDEV_POP(prev_race_points) OVER(), 0) AS prev_race_points_scaled,
    (prev_race_driver_championship_points - AVG(prev_race_driver_championship_points) OVER()) / NULLIF(STDDEV_POP(prev_race_driver_championship_points) OVER(), 0) AS prev_race_driver_championship_points_scaled,
    (prev_race_driver_championship_position - AVG(prev_race_driver_championship_position) OVER()) / NULLIF(STDDEV_POP(prev_race_driver_championship_position) OVER(), 0) AS prev_race_driver_championship_position_scaled,
    (prev_race_driver_wins - AVG(prev_race_driver_wins) OVER()) / NULLIF(STDDEV_POP(prev_race_driver_wins) OVER(), 0) AS prev_race_driver_wins_scaled,
    (prev_race_team_championship_points - AVG(prev_race_team_championship_points) OVER()) / NULLIF(STDDEV_POP(prev_race_team_championship_points) OVER(), 0) AS prev_race_team_championship_points_scaled,
    (prev_race_team_championship_position - AVG(prev_race_team_championship_position) OVER()) / NULLIF(STDDEV_POP(prev_race_team_championship_position) OVER(), 0) AS prev_race_team_championship_position_scaled,
    (prev_race_team_wins - AVG(prev_race_team_wins) OVER()) / NULLIF(STDDEV_POP(prev_race_team_wins) OVER(), 0) AS prev_race_team_wins_scaled,
    (prev_race_race_time_ms - AVG(prev_race_race_time_ms) OVER()) / NULLIF(STDDEV_POP(prev_race_race_time_ms) OVER(), 0) AS prev_race_race_time_ms_scaled
FROM {{ ref('prep_feature_set') }}
