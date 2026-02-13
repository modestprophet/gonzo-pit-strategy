-- Qualifying times pivoted per round_entry (Q1/Q2/Q3/QB)
-- Ports the qualifying_times CTE from data_repository.py

SELECT 
    re.id AS round_entry_id,
    MAX(CASE WHEN s.type = 'Q1' THEN se.time END) AS q1_time,
    MAX(CASE WHEN s.type = 'Q2' THEN se.time END) AS q2_time,
    MAX(CASE WHEN s.type = 'Q3' THEN se.time END) AS q3_time,
    COALESCE(
        MAX(CASE WHEN s.type = 'Q3' THEN se.position END),
        MAX(CASE WHEN s.type = 'Q2' THEN se.position END),
        MAX(CASE WHEN s.type = 'Q1' THEN se.position END),
        MAX(CASE WHEN s.type = 'QB' THEN se.position END)
    ) AS qualifying_position
FROM {{ source('f1db', 'session_entries') }} se
JOIN {{ source('f1db', 'sessions') }} s ON se.session_id = s.id
JOIN {{ source('f1db', 'round_entries') }} re ON se.round_entry_id = re.id
WHERE s.type IN ('Q1', 'Q2', 'Q3', 'QB')
GROUP BY re.id
