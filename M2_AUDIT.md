# Module 2 Submission Audit

The final local regression run passed **101 tests** (`python -m pytest -q`).

The additionally written test file `tests/test_m2_submission_audit.py` covers:
- bag-correct duplicate-key output for nested-loop, merge, and hash joins at B=4,5,16;
- nested group-by/AVG followed by a disk-backed sort, plus hash distinct;
- early LIMIT on a sort and join, with temporary-file cleanup;
- empty scans through sorting, distinct, grouping, and all three joins;
- malformed plans and invalid attribute references;
- set operations on inputs with duplicates;
- equal counters when repeating the same sort;
- global empty COUNT semantics and error on undefined AVG.

CLI verification:

```bash
python exec.py run --db /path/to/fixture --plan examples/m2_join_plan.json --frames 4 --json
python exec.py trace --db /path/to/fixture --plan examples/m2_join_plan.json --frames 4
```

**Known grading risks remain.** This implementation uses staging, so its exact I/O can differ from textbook cost formulas. It lacks a global runtime peak-frame tracker, and the separately published instructor plan-schema files were not available for testing. Consequently, the passing tests are not a guarantee of full marks.
