-- Derived features as views. Thresholds come from rule_registry, never constants.
-- Replace :as_of with a date literal (e.g. '2026-10-23') or bind it from your app.

DROP VIEW IF EXISTS v_student_overview;
DROP VIEW IF EXISTS v_placement_eligible;
DROP VIEW IF EXISTS v_backlog_check;
DROP VIEW IF EXISTS v_latest_attempt;
DROP VIEW IF EXISTS v_marks_gap;
DROP VIEW IF EXISTS v_attendance_status;
DROP VIEW IF EXISTS v_attendance_pct;
DROP VIEW IF EXISTS v_active_rule;

CREATE VIEW v_active_rule AS
SELECT parameter, CAST(value AS REAL) AS value, rule_id, scope_programmes, scope_batches
FROM rule_registry
WHERE effective_from <= date('now')
  AND (effective_to IS NULL OR effective_to = '' OR effective_to >= date('now'));

CREATE VIEW v_attendance_pct AS
SELECT a.student_id, a.course_code, a.classes_held, a.classes_attended,
       ROUND(100.0*a.classes_attended/a.classes_held, 2) AS attendance_pct,
       COALESCE((SELECT value FROM v_active_rule WHERE parameter='min_attendance_pct'), 75.0) AS threshold_pct
FROM attendance a;

CREATE VIEW v_attendance_status AS
SELECT *,
  attendance_pct >= threshold_pct AS eligible,
  -- Future classes needed to reach threshold accounting for growing total held classes: ceil((T*held - attended) / (1 - T))
  MAX(0, CAST(((threshold_pct / 100.0 * classes_held - classes_attended) / (1.0 - threshold_pct / 100.0) + 0.999999) AS INTEGER)) AS classes_short_by,
  -- Classes that can still be missed out of the classes already held (floor)
  MAX(0, CAST(classes_attended - threshold_pct / 100.0 * classes_held AS INTEGER)) AS surplus_classes
FROM v_attendance_pct;

CREATE VIEW v_marks_gap AS
SELECT r.student_id, r.course_code, r.total_marks, r.result,
       COALESCE(
           (SELECT value FROM v_active_rule WHERE parameter='min_total_marks'),
           (SELECT value FROM v_active_rule WHERE parameter='min_pass_total_pct') * r.max_marks / 100.0,
           40.0
       ) - r.total_marks AS marks_to_pass
FROM results r WHERE r.result='FAIL';

CREATE VIEW v_latest_attempt AS
SELECT * FROM results r
WHERE NOT EXISTS (
  SELECT 1 FROM results x
  WHERE x.student_id = r.student_id AND x.course_code = r.course_code
    AND (
      -- Newer exam session year
      CAST(substr(x.exam_session, 1, 4) AS INTEGER) > CAST(substr(r.exam_session, 1, 4) AS INTEGER)
      OR (
        CAST(substr(x.exam_session, 1, 4) AS INTEGER) = CAST(substr(r.exam_session, 1, 4) AS INTEGER)
        AND (
          -- Newer exam session month within same year
          (CASE substr(x.exam_session, 6) WHEN 'JAN' THEN 1 WHEN 'FEB' THEN 2 WHEN 'MAR' THEN 3 WHEN 'APR' THEN 4 WHEN 'MAY' THEN 5 WHEN 'JUN' THEN 6 WHEN 'JUL' THEN 7 WHEN 'AUG' THEN 8 WHEN 'SEP' THEN 9 WHEN 'OCT' THEN 10 WHEN 'NOV' THEN 11 WHEN 'DEC' THEN 12 ELSE 0 END)
          >
          (CASE substr(r.exam_session, 6) WHEN 'JAN' THEN 1 WHEN 'FEB' THEN 2 WHEN 'MAR' THEN 3 WHEN 'APR' THEN 4 WHEN 'MAY' THEN 5 WHEN 'JUN' THEN 6 WHEN 'JUL' THEN 7 WHEN 'AUG' THEN 8 WHEN 'SEP' THEN 9 WHEN 'OCT' THEN 10 WHEN 'NOV' THEN 11 WHEN 'DEC' THEN 12 ELSE 0 END)
          OR (
            -- Same year and month: SUPPLEMENTARY or MAKEUP beats REGULAR
            (CASE substr(x.exam_session, 6) WHEN 'JAN' THEN 1 WHEN 'FEB' THEN 2 WHEN 'MAR' THEN 3 WHEN 'APR' THEN 4 WHEN 'MAY' THEN 5 WHEN 'JUN' THEN 6 WHEN 'JUL' THEN 7 WHEN 'AUG' THEN 8 WHEN 'SEP' THEN 9 WHEN 'OCT' THEN 10 WHEN 'NOV' THEN 11 WHEN 'DEC' THEN 12 ELSE 0 END)
            =
            (CASE substr(r.exam_session, 6) WHEN 'JAN' THEN 1 WHEN 'FEB' THEN 2 WHEN 'MAR' THEN 3 WHEN 'APR' THEN 4 WHEN 'MAY' THEN 5 WHEN 'JUN' THEN 6 WHEN 'JUL' THEN 7 WHEN 'AUG' THEN 8 WHEN 'SEP' THEN 9 WHEN 'OCT' THEN 10 WHEN 'NOV' THEN 11 WHEN 'DEC' THEN 12 ELSE 0 END)
            AND (x.exam_type IN ('SUPPLEMENTARY', 'MAKEUP') AND r.exam_type = 'REGULAR')
          )
        )
      )
    )
);

CREATE VIEW v_backlog_check AS
SELECT s.student_id, s.active_backlogs AS stored,
       (SELECT COUNT(*) FROM v_latest_attempt l WHERE l.student_id=s.student_id AND l.result<>'PASS') AS computed
FROM students s;

CREATE VIEW v_placement_eligible AS
SELECT student_id, full_name, cgpa, active_backlogs,
       cgpa >= COALESCE((SELECT value FROM v_active_rule WHERE parameter='placement_min_cgpa'), 7.00) AS cgpa_ok
FROM students;

CREATE VIEW v_student_overview AS
SELECT s.student_id, s.full_name, s.programme, s.batch_year, s.cgpa, s.active_backlogs,
       ROUND(100.0*SUM(a.classes_attended)/SUM(a.classes_held),2) AS overall_attendance_pct,
       MIN(100.0*a.classes_attended/a.classes_held) AS lowest_course_attendance_pct
FROM students s JOIN attendance a USING(student_id) GROUP BY s.student_id;
