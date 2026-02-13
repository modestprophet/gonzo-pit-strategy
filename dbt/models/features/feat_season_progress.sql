-- Season progress: what fraction of the season has elapsed
-- Replaces SeasonProgress (step 8)

SELECT
    *,
    round_number::float / NULLIF(MAX(round_number) OVER (PARTITION BY season_year), 0) 
        AS season_progress_percent
FROM {{ ref('feat_lagged') }}
