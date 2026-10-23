-- Seed rules for DTU rule_registry table
-- All thresholds trace back to cited authentic DTU clauses

DELETE FROM rule_registry;

INSERT INTO rule_registry (rule_id, description, parameter, operator, value, scope_programmes, scope_batches, effective_from, effective_to, source_doc_id, source_section) VALUES
('ATT-MIN-01', 'Minimum attendance required to appear in End-Term Examinations', 'min_attendance_pct', '>=', '75.0', 'ALL', 'ALL', '2024-07-01', '', 'DTU-ORD-2024', 'Clause R.1(B).22'),
('ATT-COND-MED', 'Medical condonation threshold allowed by Dean Academic upon certified medical leave', 'medical_condonation_pct', '>=', '65.0', 'ALL', 'ALL', '2024-07-01', '2026-07-31', 'DTU-ORD-2024', 'Clause R.1(B).22(iii)'),
('ATT-COND-MED-2026', 'Amended medical condonation threshold under Dean Academic notification 2026', 'medical_condonation_pct', '>=', '70.0', 'ALL', 'ALL', '2026-08-01', '', 'DTU-SYN-AMEND-2026', 'Section 1'),
('CWS-ATT-5', 'Full 5 marks in CWS attendance component (95.0% - 100.0%)', 'cws_attendance_tier', 'between', '95.0,100.0', 'ALL', 'ALL', '2024-07-15', '', 'DTU-CIR-ATT-2024', 'Section 2'),
('CWS-ATT-4', '4 marks in CWS attendance component (90.0% - 94.99%)', 'cws_attendance_tier', 'between', '90.0,94.99', 'ALL', 'ALL', '2024-07-15', '', 'DTU-CIR-ATT-2024', 'Section 2'),
('CWS-ATT-3', '3 marks in CWS attendance component (85.0% - 89.99%)', 'cws_attendance_tier', 'between', '85.0,89.99', 'ALL', 'ALL', '2024-07-15', '', 'DTU-CIR-ATT-2024', 'Section 2'),
('CWS-ATT-2', '2 marks in CWS attendance component (80.0% - 84.99%)', 'cws_attendance_tier', 'between', '80.0,84.99', 'ALL', 'ALL', '2024-07-15', '', 'DTU-CIR-ATT-2024', 'Section 2'),
('CWS-ATT-1', '1 mark in CWS attendance component (75.0% - 79.99%)', 'cws_attendance_tier', 'between', '75.0,79.99', 'ALL', 'ALL', '2024-07-15', '', 'DTU-CIR-ATT-2024', 'Section 2'),
('EXAM-PASS-MIN', 'Minimum total marks required to pass a theory course', 'min_pass_total_pct', '>=', '40.0', 'ALL', 'ALL', '2024-07-01', '', 'DTU-ORD-2024', 'Clause R.1(B).18'),
('PROMO-MAX-BACKLOG', 'Maximum permissible backlogs to register for 5th semester (3rd year)', 'max_backlogs_promotion', '<=', '4', 'B.Tech CSE,B.Tech IT,B.Tech ECE', 'ALL', '2024-07-01', '', 'DTU-ORD-2024', 'Clause R.1(B).15'),
('SUPP-ELIG-FAIL', 'Supplementary examination eligibility for students failing theory course', 'supplementary_eligible_grade', '==', 'FAIL', 'ALL', 'ALL', '2024-08-01', '', 'DTU-CIR-EXAM-SUPP', 'Section 1'),
('SUPP-BAR-DETAIN', 'Students detained due to attendance shortage barred from supplementary exam', 'supplementary_prohibited_status', '==', 'DETAINED', 'ALL', 'ALL', '2024-08-01', '', 'DTU-CIR-EXAM-SUPP', 'Section 1'),
('PLACE-MIN-CGPA', 'Minimum CGPA required to register for campus placement drives', 'placement_min_cgpa', '>=', '6.0', 'ALL', 'ALL', '2024-07-01', '', 'DTU-ORD-2024', 'Clause R.1(B).28'),
('PLACE-MAX-BACKLOG', 'Maximum permissible active backlogs for campus placement registration', 'placement_max_active_backlogs', '<=', '0', 'ALL', 'ALL', '2024-07-01', '', 'DTU-ORD-2024', 'Clause R.1(B).28');
