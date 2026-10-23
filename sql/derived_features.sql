-- Derived features as views. Thresholds come from rule_registry, never constants.
-- Replace :as_of with a date literal (e.g. '2026-10-23') or bind it from your app.
CREATE VIEW IF NOT EXISTS v_active_rule AS
SELECT parameter, CAST(value AS REAL) AS value, rule_id, scope_programmes, scope_batches
FROM rule_registry
WHERE effective_from <= date('now')
  AND (effective_to IS NULL OR effective_to = '' OR effective_to >= date('now'));

CREATE VIEW IF NOT EXISTS v_attendance_pct AS
SELECT a.student_id, a.course_code, a.classes_held, a.classes_attended,
       ROUND(100.0*a.classes_attended/a.classes_held, 2) AS attendance_pct,
       (SELECT value FROM v_active_rule WHERE parameter='min_attendance_pct') AS threshold_pct
FROM attendance a;

CREATE VIEW IF NOT EXISTS v_attendance_status AS
SELECT *,
  attendance_pct >= threshold_pct AS eligible,
  -- classes still needed to reach the threshold if all remaining are attended (ceil)
  MAX(0, CAST((threshold_pct/100.0*classes_held - classes_attended + 0.999999) AS INTEGER)) AS classes_short_by,
  -- classes that can still be missed out of the classes already held (floor)
  MAX(0, CAST(classes_attended - threshold_pct/100.0*classes_held AS INTEGER)) AS surplus_classes
FROM v_attendance_pct;

CREATE VIEW IF NOT EXISTS v_marks_gap AS
SELECT r.student_id, r.course_code, r.total_marks, r.result,
       (SELECT value FROM v_active_rule WHERE parameter='min_total_marks') - r.total_marks AS marks_to_pass
FROM results r WHERE r.result='FAIL';

CREATE VIEW IF NOT EXISTS v_latest_attempt AS
SELECT * FROM results r
WHERE NOT EXISTS (SELECT 1 FROM results x
  WHERE x.student_id=r.student_id AND x.course_code=r.course_code
    AND ((x.exam_type='SUPPLEMENTARY' AND r.exam_type='REGULAR')
      OR (x.exam_type=r.exam_type AND x.exam_session>r.exam_session)));

CREATE VIEW IF NOT EXISTS v_backlog_check AS
SELECT s.student_id, s.active_backlogs AS stored,
       (SELECT COUNT(*) FROM v_latest_attempt l WHERE l.student_id=s.student_id AND l.result<>'PASS') AS computed
FROM students s;

CREATE VIEW IF NOT EXISTS v_placement_eligible AS
SELECT student_id, full_name, cgpa, active_backlogs,
       cgpa >= (SELECT value FROM v_active_rule WHERE parameter='placement_min_cgpa') AS cgpa_ok
FROM students;

CREATE VIEW IF NOT EXISTS v_student_overview AS
SELECT s.student_id, s.full_name, s.programme, s.batch_year, s.cgpa, s.active_backlogs,
       ROUND(100.0*SUM(a.classes_attended)/SUM(a.classes_held),2) AS overall_attendance_pct,
       MIN(100.0*a.classes_attended/a.classes_held) AS lowest_course_attendance_pct
FROM students s JOIN attendance a USING(student_id) GROUP BY s.student_id;
