-- Race session results joined with driver/team/circuit info
-- Ports the race_results CTE from data_repository.py

SELECT 
    r.id AS round_id,
    r.circuit_id,
    c.name AS circuit_name,
    sn.year AS season_year,
    r.date AS round_date,
    r.number AS round_number,
    r.wikipedia AS round_url,
    t.id AS team_id,
    t.name AS team_name,
    d.id AS driver_id,
    d.abbreviation AS driver_abbreviation,
    re.id AS round_entry_id,
    se.grid,
    se.position AS finish_position,
    se.status,
    se.detail AS status_detail,
    se.laps_completed,
    se.points,
    se.time,
    se.fastest_lap_rank
FROM {{ source('f1db', 'session_entries') }} se
JOIN {{ source('f1db', 'sessions') }} s ON se.session_id = s.id
JOIN {{ source('f1db', 'rounds') }} r ON s.round_id = r.id
JOIN {{ source('f1db', 'seasons') }} sn ON r.season_id = sn.id
JOIN {{ source('f1db', 'circuits') }} c ON r.circuit_id = c.id
JOIN {{ source('f1db', 'round_entries') }} re ON se.round_entry_id = re.id
JOIN {{ source('f1db', 'team_drivers') }} td ON re.team_driver_id = td.id
JOIN {{ source('f1db', 'drivers') }} d ON td.driver_id = d.id
JOIN {{ source('f1db', 'teams') }} t ON td.team_id = t.id
WHERE s.type = 'R'
  AND r.is_cancelled = false
