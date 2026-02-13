-- Z-score clip outliers at 3 standard deviations
-- Replaces ZScoreClipper (step 9)

SELECT
    -- Pass through non-clipped columns
    round_id, circuit_id, circuit_name, season_year, round_date, round_number,
    round_url, team_id, team_name, driver_id, driver_abbreviation,
    q1_time, q2_time, q3_time, time, status, status_detail,
    laps_completed, fastest_lap_rank,
    q1_seconds, q1_time_missing, q2_seconds, q2_time_missing,
    q3_seconds, q3_time_missing, race_time_ms,
    is_dnf, finish_position_filled,
    prev_race_points, prev_race_driver_championship_points,
    prev_race_driver_championship_position, prev_race_driver_wins,
    prev_race_team_championship_points, prev_race_team_championship_position,
    prev_race_team_wins, prev_race_race_time_ms,
    season_progress_percent,
    driver_wins, team_wins,
    driver_championship_position,
    team_championship_position,
    
    -- Clipped columns (matching the current pipeline config)
    {{ z_score_clip('qualifying_position') }} AS qualifying_position,
    {{ z_score_clip('grid') }} AS grid,
    {{ z_score_clip('finish_position_filled') }} AS finish_position,
    {{ z_score_clip('race_time_ms') }} AS race_time_ms_clipped,
    {{ z_score_clip('points') }} AS points,
    {{ z_score_clip('driver_championship_points') }} AS driver_championship_points,
    {{ z_score_clip('team_championship_points') }} AS team_championship_points
FROM {{ ref('feat_season_progress') }}
