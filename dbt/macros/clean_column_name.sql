{% macro clean_column_name(text) %}
    {{- text | replace('&amp;', 'and') | replace('&', 'and') | replace(' ', '_') | replace('-', '_') | replace("'", '') | replace('.', '') | replace('(', '') | replace(')', '') | replace('/', '_') | replace(';', '') | lower -}}
{% endmacro %}
