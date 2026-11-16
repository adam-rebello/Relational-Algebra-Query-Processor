CREATE TABLE DemoDept (did INT, title VARCHAR(20));
INSERT INTO DemoDept VALUES (10, 'CS');
INSERT INTO DemoDept VALUES (20, 'Math');
SELECT s.name, d.title FROM DemoStudents s JOIN DemoDept d ON s.dept = d.did WHERE s.id > 1;
EXPLAIN ANALYZE SELECT s.name, d.title FROM DemoStudents s JOIN DemoDept d ON s.dept = d.did WHERE s.id > 1;
