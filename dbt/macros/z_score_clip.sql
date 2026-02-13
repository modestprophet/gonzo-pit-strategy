{% macro z_score_clip(column_name, threshold=3.0) %}
    CASE
        WHEN STDDEV({{ column_name }}) OVER() = 0 THEN {{ column_name }}
        WHEN ({{ column_name }} - AVG({{ column_name }}) OVER()) 
             / STDDEV({{ column_name }}) OVER() > {{ threshold }}
        THEN AVG({{ column_name }}) OVER() + {{ threshold }} * STDDEV({{ column_name }}) OVER()
        WHEN ({{ column_name }} - AVG({{ column_name }}) OVER()) 
             / STDDEV({{ column_name }}) OVER() < -{{ threshold }}
        THEN AVG({{ column_name }}) OVER() - {{ threshold }} * STDDEV({{ column_name }}) OVER()
        ELSE {{ column_name }}
    END
{% endmacro %}
