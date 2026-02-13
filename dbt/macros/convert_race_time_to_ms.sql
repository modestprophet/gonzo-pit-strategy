{% macro convert_race_time_to_ms(column_name) %}
    CASE
        WHEN {{ column_name }} IS NULL OR {{ column_name }} = '0:00.000' THEN 0.0
        -- Format: H:MM:SS.fff
        WHEN {{ column_name }} ~ '^\d+:\d{2}:\d{2}\.\d+$' THEN
            SPLIT_PART({{ column_name }}, ':', 1)::float * 3600000.0
            + SPLIT_PART(SPLIT_PART({{ column_name }}, ':', 2), ':', 1)::float * 60000.0
            + SPLIT_PART({{ column_name }}, ':', 3)::float * 1000.0
        -- Format: M:SS.fff
        WHEN {{ column_name }} ~ '^\d+:\d{2}\.\d+$' THEN
            SPLIT_PART({{ column_name }}, ':', 1)::float * 60000.0
            + SPLIT_PART({{ column_name }}, ':', 2)::float * 1000.0
        -- Bare seconds
        WHEN {{ column_name }} ~ '^\d+\.?\d*$' THEN
            {{ column_name }}::float * 1000.0
        ELSE 0.0
    END
{% endmacro %}
