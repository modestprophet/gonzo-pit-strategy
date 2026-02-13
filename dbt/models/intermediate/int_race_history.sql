-- Full race history with qualifying and championship standings
-- Joins all 4 staging models - ports the final SELECT from data_repository.py
-- Also handles null filling (replaces NullValueCleaner) and type casting (replaces DataTypeConverter)

SELECT 
    rr.round_id,
    rr.circuit_id,
    rr.circuit_name,
    rr.season_year,
    rr.round_date,
    rr.round_number,
    rr.round_url,
    rr.team_id,
    rr.team_name,
    rr.driver_id,
    rr.driver_abbreviation,
    -- Null filling for qualifying times (replaces NullValueCleaner step 1)
    COALESCE(qt.q1_time, '0:00.000') AS q1_time,
    COALESCE(qt.q2_time, '0:00.000') AS q2_time,
    COALESCE(qt.q3_time, '0:00.000') AS q3_time,
    -- Type conversion and null filling (replaces DataTypeConverter step 2)
    COALESCE(qt.qualifying_position, 50)::numeric AS qualifying_position,
    rr.grid,
    rr.finish_position,
    rr.status,
    rr.status_detail,
    rr.laps_completed,
    rr.points::numeric AS points,
    rr.time,
    rr.fastest_lap_rank,
    ds.driver_championship_points::numeric AS driver_championship_points,
    ds.driver_championship_position::numeric AS driver_championship_position,
    ds.driver_wins,
    ts.team_championship_points::numeric AS team_championship_points,
    ts.team_championship_position::numeric AS team_championship_position,
    ts.team_wins
FROM {{ ref('stg_race_results') }} rr
LEFT JOIN {{ ref('stg_qualifying') }} qt 
    ON rr.round_entry_id = qt.round_entry_id
LEFT JOIN {{ ref('stg_driver_standings') }} ds 
    ON rr.round_id = ds.round_id AND rr.driver_id = ds.driver_id
LEFT JOIN {{ ref('stg_team_standings') }} ts 
    ON rr.round_id = ts.round_id AND rr.team_id = ts.team_id
ORDER BY rr.season_year, rr.round_number, rr.finish_position NULLS LAST
