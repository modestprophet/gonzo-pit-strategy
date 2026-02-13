-- One-hot encode team_name (step 2 of 3)
-- Custom implementation to handle special characters in names
-- Replaces CategoricalEncoder (step 5) for team_name

{% set teams_query %}
    SELECT DISTINCT team_name 
    FROM {{ ref('prep_ohe_circuit') }}
    ORDER BY team_name
{% endset %}

{% set results = run_query(teams_query) %}
{% if execute %}
    {% set teams = results.columns[0].values() %}
{% else %}
    {% set teams = [] %}
{% endif %}

SELECT
    -- Pass through all columns except team_name using dbt_utils.star
    {{ dbt_utils.star(ref('prep_ohe_circuit'), except=["team_name"]) }},
    
    -- One-hot encoded team columns
    {% for team in teams %}
    CASE WHEN team_name = '{{ team }}' THEN 1 ELSE 0 END AS team_{{ clean_column_name(team) }}
    {% if not loop.last %},{% endif %}
    {% endfor %}
FROM {{ ref('prep_ohe_circuit') }}
