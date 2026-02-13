{% macro convert_lap_time_to_seconds(column_name) %}
    CASE
        WHEN {{ column_name }} IS NULL OR {{ column_name }} = '0:00.000' THEN 0.0
        WHEN {{ column_name }} ~ '^\d+:\d+\.\d+$' THEN
            SPLIT_PART({{ column_name }}, ':', 1)::float * 60.0
            + SPLIT_PART({{ column_name }}, ':', 2)::float
        ELSE 0.0
    END
{% endmacro %}
