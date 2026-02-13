-- Team championship standings after each round's race session
-- Ports the team_standings CTE from data_repository.py

SELECT DISTINCT ON (tc.round_id, tc.team_id)
    tc.round_id,
    tc.team_id,
    tc.points AS team_championship_points,
    tc.position AS team_championship_position,
    tc.win_count AS team_wins
FROM {{ source('f1db', 'team_championships') }} tc
JOIN {{ source('f1db', 'sessions') }} s ON tc.session_id = s.id
WHERE s.type = 'R'
ORDER BY tc.round_id, tc.team_id, tc.session_number DESC
