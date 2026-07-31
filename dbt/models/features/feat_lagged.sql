-- Lagged features: previous race values per driver per season
-- Replaces LaggedFeatureGenerator (step 7)
-- Uses native SQL LAG() window functions - this is where SQL shines!
--
-- KNOWN LIMITATION (accepted, not fixed) — the window's ORDER BY is not unique.
-- 83 groups / 172 rows in seasons 1950-1964 have a driver entered more than once
-- in a single round (historical shared drives), and SQL does not define which
-- tied row LAG returns. prev_race_points, prev_race_team_wins and
-- prev_race_race_time_ms therefore vary with physical row order, which is why
-- two independently-built copies of this database produce different dataset
-- fingerprints. Filtering to seasons >= 2008 removes every tied group.
-- Tracked by the warn-severity uniqueness test on feat_dnf_handled in schema.yml.

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
