-- One-hot encode driver_abbreviation (step 3 of 3)
-- Custom implementation to handle special characters in names
-- Replaces CategoricalEncoder (step 5) for driver_abbreviation

{% set drivers_query %}
    SELECT DISTINCT driver_abbreviation 
    FROM {{ ref('prep_ohe_team') }}
    ORDER BY driver_abbreviation
{% endset %}

{% set results = run_query(drivers_query) %}
{% if execute %}
    {% set drivers = results.columns[0].values() %}
{% else %}
    {% set drivers = [] %}
{% endif %}

SELECT
    -- Pass through all columns except driver_abbreviation using dbt_utils.star
    {{ dbt_utils.star(ref('prep_ohe_team'), except=["driver_abbreviation"]) }},
    
    -- One-hot encoded driver columns
    {% for driver in drivers %}
    CASE WHEN driver_abbreviation = '{{ driver }}' THEN 1 ELSE 0 END AS driver_{{ clean_column_name(driver) }}
    {% if not loop.last %},{% endif %}
    {% endfor %}
FROM {{ ref('prep_ohe_team') }}
