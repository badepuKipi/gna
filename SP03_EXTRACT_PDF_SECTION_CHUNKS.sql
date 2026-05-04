CREATE OR REPLACE PROCEDURE UKG_TLM_DB.TLM_CONFIG.SP03_EXTRACT_PDF_SECTION_CHUNKS("P_BATCH_ID" VARCHAR)
RETURNS VARCHAR
LANGUAGE SQL
EXECUTE AS CALLER
AS '
BEGIN

DELETE FROM UKG_TLM_DB.TLM_CONFIG.TBL_PDFS_SECTIONS_CHUNKS
WHERE CLIENT_NAME IN (
    SELECT DISTINCT CLIENT_NAME
    FROM UKG_TLM_DB.TLM_CONFIG.TBL_PARSED_PDFS
    WHERE BATCH_ID = :P_BATCH_ID
);

INSERT INTO UKG_TLM_DB.TLM_CONFIG.TBL_PDFS_SECTIONS_CHUNKS
    (CLIENT_NAME, SECTION_NAME, SECTION_CONTENT, EXTRACTED_AT, BATCH_ID)

WITH base AS (
  SELECT PARSED_CONTENT, CLIENT_NAME
  FROM UKG_TLM_DB.TLM_CONFIG.TBL_PARSED_PDFS
  WHERE BATCH_ID = :P_BATCH_ID
),

section_markers AS (
  SELECT CLIENT_NAME, f.value::STRING AS start_marker
  FROM base,
  LATERAL FLATTEN(INPUT => REGEXP_EXTRACT_ALL(PARSED_CONTENT, ''^#{1,3} [^\\n]+'', 1, 1, ''m'')) f
),

section_positions AS (
  SELECT
    b.CLIENT_NAME,
    b.PARSED_CONTENT,
    s.start_marker,
    TRIM(REGEXP_REPLACE(s.start_marker, ''^#{1,3} '', '''')) AS section_name,
    POSITION(s.start_marker IN b.PARSED_CONTENT) AS start_pos
  FROM base b
  JOIN section_markers s ON b.CLIENT_NAME = s.CLIENT_NAME
  WHERE POSITION(s.start_marker IN b.PARSED_CONTENT) > 0
  QUALIFY ROW_NUMBER() OVER (PARTITION BY b.CLIENT_NAME, TRIM(REGEXP_REPLACE(s.start_marker, ''^#{1,3} '', '''')) ORDER BY POSITION(s.start_marker IN b.PARSED_CONTENT)) = 1
),

ordered_sections AS (
  SELECT *,
    LEAD(start_pos) OVER (PARTITION BY CLIENT_NAME ORDER BY start_pos) AS next_pos
  FROM section_positions
),

section_extraction AS (
  SELECT
    CLIENT_NAME,
    section_name,
    SUBSTR(
      PARSED_CONTENT,
      start_pos,
      COALESCE(next_pos, LENGTH(PARSED_CONTENT)) - start_pos
    ) AS section_content
  FROM ordered_sections
),

profile_sections AS (
  SELECT
    CLIENT_NAME,
    TRIM(SPLIT_PART(value, ''\\n'', 1)) AS section_name,
    value AS section_content
  FROM base,
  LATERAL FLATTEN(INPUT => SPLIT(PARSED_CONTENT, ''Pay Calculation Profile:''))
),

counter_details AS (
  SELECT
    CLIENT_NAME,
    TRIM(REGEXP_SUBSTR(value, ''^[^\\n]+'')) AS section_name,
    value AS section_content
  FROM section_extraction,
  LATERAL FLATTEN(
    INPUT => SPLIT(
      REGEXP_REPLACE(section_content, ''\\\\n(Counter Name:|Name:)'', ''|||SPLIT|||\\1''),
      ''|||SPLIT|||''
    )
  )
  WHERE section_name = ''Counters''
    AND TRIM(value) != ''''
)

SELECT
  CLIENT_NAME,
  section_name,
  section_content,
  CURRENT_TIMESTAMP(),
  :P_BATCH_ID
FROM section_extraction

UNION ALL

SELECT
  CLIENT_NAME,
  section_name,
  section_content,
  CURRENT_TIMESTAMP(),
  :P_BATCH_ID
FROM profile_sections

UNION ALL

SELECT
  CLIENT_NAME,
  section_name,
  section_content,
  CURRENT_TIMESTAMP(),
  :P_BATCH_ID
FROM counter_details;

RETURN ''SUCCESS'';

EXCEPTION
    WHEN OTHER THEN
        INSERT INTO UKG_TLM_DB.TLM_CONFIG.TBL_PARSE_PDF_LOGS (LOG_LEVEL, MESSAGE, ERROR_MESSAGE)
        VALUES (''ERROR'', ''SP03_EXTRACT_PDF_SECTION_CHUNKS failed'', ''See TASK_HISTORY for error details'');
        RAISE;

END;
';