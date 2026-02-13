-- Driver championship standings after each round's race session
-- Ports the driver_standings CTE from data_repository.py

SELECT DISTINCT ON (dc.round_id, dc.driver_id)
    dc.round_id,
    dc.driver_id,
    dc.points AS driver_championship_points,
    dc.position AS driver_championship_position,
    dc.win_count AS driver_wins
FROM {{ source('f1db', 'driver_championships') }} dc
JOIN {{ source('f1db', 'sessions') }} s ON dc.session_id = s.id
WHERE s.type = 'R'
ORDER BY dc.round_id, dc.driver_id, dc.session_number DESC
