-- Handle DNF: create is_dnf flag, fill null finish_position with 25
-- Replaces DNFHandler (step 8)

SELECT
    *,
    CASE WHEN finish_position IS NULL THEN 1 ELSE 0 END AS is_dnf,
    COALESCE(finish_position, 25)::numeric AS finish_position_filled
FROM {{ ref('feat_time_converted') }}
