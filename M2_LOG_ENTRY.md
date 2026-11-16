## Project 2 — M2 checkpoint (add actual development dates from Git history)

### Iterators and the first runnable plan

I started with a small execution-tree API (`open`, `next`, `close`, `counters`) and connected sequential scans to the Module 1 heap file. I then added pipelined filter, projection, LIMIT and UNION ALL. I tested these against actual disk-backed tables, including a case where a projection must preserve duplicate rows rather than removing them as Bonus Project 1 did.

### Blocking operators and the memory budget

I added temporary 4096-byte page files through the Module 1 disk manager. The external sort writes bounded initial runs and merges at most B-1 runs at a time. Distinct and group-by support sort-based and hash-partitioned variants. Block nested loop, sort-merge and Grace hash join are separate algorithms rather than aliases for one tuple-at-a-time join.

The implementation uses conservative frame reservations and input staging to avoid assuming a full table fits in memory. I compared the resulting measured I/O to the textbook formulas and documented the staging overhead in `REPORT_M2.md`.

### AI-assisted corrections verified through testing

1. **Unbounded CLI result list:** An intermediate runner collected every result tuple into a Python list before printing JSON. Reviewing the assignment's memory rule showed this would violate B when a query returned many rows. I changed `exec.py` to write JSON rows incrementally, then reran the tests and CLI query.
2. **Hash-join partition budget:** An initial partition loop kept the Module 1 heap scan active while reserving B-1 output partitions. The live directory/data pages could push that over B. I changed the partition phase to stage the child once, then consume one temporary input page alongside B-1 partition output pages.
3. **Missing operator validation:** The first partial implementation deliberately rejected hash join, and its original test expected that error. After implementing the algorithm, the old test failed. I updated it to verify a genuinely missing required field instead of expecting an implemented operator to be unsupported.
4. **Test harness naming issue:** An additional test class overrode unittest's `run` method with a query runner, which caused pytest to fail before testing the database code. I renamed the helper to `run_plan` and reran the suite.

### Measurements, results, and limitations

The combined test suite passed 85 tests in the local environment. I ran 36 join-size/frame experiments, six external-sort trials and a 40% skew hash-join case. A B=4 external-sort trial processed 88 input pages, more than 20 times its four-frame budget. The skew test used the on-disk fallback for an oversized partition and returned the expected 6,520 matches.

The separate full plan JSON schema mentioned in the M2 PDF was not supplied, and the implementation has not been tested against it. Some I/O counts are higher than ideal textbook costs because of temporary-file staging, and a global peak-frame monitor remains unimplemented. These limits are stated in the design and report rather than treated as passing requirements.
