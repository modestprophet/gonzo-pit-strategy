-- Lagged features: previous race values per driver per season
-- Replaces LaggedFeatureGenerator (step 7)
-- Uses native SQL LAG() window functions - this is where SQL shines!

SELECT
    *,
    COALESCE(LAG(points, 1) OVER w, 0) AS prev_race_points,
    COALESCE(LAG(driver_championship_points, 1) OVER w, 0) AS prev_race_driver_championship_points,
    COALESCE(LAG(driver_championship_position, 1) OVER w, 0) AS prev_race_driver_championship_position,
    COALESCE(LAG(driver_wins, 1) OVER w, 0) AS prev_race_driver_wins,
    COALESCE(LAG(team_championship_points, 1) OVER w, 0) AS prev_race_team_championship_points,
    COALESCE(LAG(team_championship_position, 1) OVER w, 0) AS prev_race_team_championship_position,
    COALESCE(LAG(team_wins, 1) OVER w, 0) AS prev_race_team_wins,
    COALESCE(LAG(race_time_ms, 1) OVER w, 0) AS prev_race_race_time_ms
FROM {{ ref('feat_dnf_handled') }}
WINDOW w AS (PARTITION BY season_year, driver_id ORDER BY round_number)
