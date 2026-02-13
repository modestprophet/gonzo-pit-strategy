-- Convert qualifying time strings to seconds, race time to milliseconds
-- Replaces QualifyingTimeConverter (step 3) and RaceTimeConverter (step 4)

SELECT
    *,
    {{ convert_lap_time_to_seconds('q1_time') }} AS q1_seconds,
    CASE WHEN q1_time = '0:00.000' THEN 1 ELSE 0 END AS q1_time_missing,
    {{ convert_lap_time_to_seconds('q2_time') }} AS q2_seconds,
    CASE WHEN q2_time = '0:00.000' THEN 1 ELSE 0 END AS q2_time_missing,
    {{ convert_lap_time_to_seconds('q3_time') }} AS q3_seconds,
    CASE WHEN q3_time = '0:00.000' THEN 1 ELSE 0 END AS q3_time_missing,
    {{ convert_race_time_to_ms('time') }} AS race_time_ms
FROM {{ ref('int_race_history') }}
