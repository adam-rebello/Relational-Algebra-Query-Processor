# DESIGN_LOG.md

## Session 1 - Grammar and Initial Design Septemeber 22nd, 2026

I started by breaking the project into the tokenizer, parser, parse tree, relation model, evaluator, tests, and performance tools. I decided to use a hand-written tokenizer and recursive-descent parser because the assignment specifically does not allow parser generators or regular expressions.

I also worked out the operator precedence before implementing the parser. Union and minus are handled at the lowest relational level, intersect is above them, join and times are above intersect, and unary operators such as select, project, and rename bind the strongest.

One issue I found while discussing the tokenizer with AI was that an early approach treated words such as union as permanently reserved keywords. That would have caused valid cases such as select[union=3](R) to fail when an attribute happens to have the same name as a keyword. I changed the design so the tokenizer produces WORD tokens and the parser decides from context whether a word is acting as an operator or an identifier.

## Session 2 - Tokenizer, Parser, and Parse Tree Septemebr 23rd, 2026

I implemented the tokenizer manually with character-by-character scanning. It supports identifiers, numbers, strings, punctuation, comparison operators, comments, and source positions. Multi-character operators such as >=, <=, and != use maximal munch.

I then implemented the recursive-descent parser using a separate function for each precedence level. I used loops for left-associative operators such as union and minus instead of directly translating left-recursive grammar rules.

I added a printable parse tree and checked it using nested queries such as:

project[Name](select[Age>30](Employees))

The grammar tests were also useful for confirming that A minus B minus C groups from the left and that condition precedence follows not, then and, then or.

## Session 3 - Relation Model and Operators September 24th, 2026 

I implemented the Relation, Attribute, and tuple classes and then added the relational operators in the evaluator. Relations use set semantics, so duplicate tuples are not inserted.

One problem caused by an earlier AI-generated version of copy_schema() was that copied attributes lost or changed their original relation qualifiers. This caused qualified attribute lookup to fail later during joins. I found the problem through semantic tests and changed copy_schema() so that it preserves the qualifier stored on each Attribute.

I also decided that projecting the same attribute more than once is treated as a schema error. This behaviour is documented and tested.

## Session 4 - Join and Self-Join Debugging September 25th, 2026

The join operator was implemented as a nested-loop theta join. For every pair of tuples, the join condition is evaluated and the join comparison counter is increased exactly once.

Another AI-generated join revision initially handled qualified attributes incorrectly. In particular, expressions involving renamed relations and self-joins could not always determine whether an attribute belonged to the left or right operand.

I found this when the required qualified join and self-join semantic tests failed. I rewrote join operand resolution so it searches the left and right schemas separately and checks the stored relation qualifier. After that correction, the full test suite passed with 32 tests.

## Session 5 - Error Handling and Command-Line Interface Septemeber 26th, 2026

I added separate error categories for lexical errors, syntax errors, unknown names, schema problems, and type errors.

The command-line program catches these errors and prints a readable message instead of exposing a Python stack trace.

I tested the tree mode with:

python ra.py --tree "project[Name](select[Age>30](Employees))"

I also tested evaluation using a relation data file and checked normal results, projection, selection, and empty results.

## Session 6 - Performance Testing September 29th, 2026

I created separate benchmark tools for join, select/project, and match-rate experiments.

The join benchmark used the required sizes from 1,000 up to 64,000 tuples on each side. The nested-loop join showed quadratic growth and the largest measured case, 64,000 by 64,000, performed 4,096,000,000 comparisons and took 8712.435958 seconds.

An early AI suggestion was to run all large benchmark sizes together before checking smaller cases. After seeing how quickly the runtime increased, I changed the process so results were saved incrementally and the largest runs were handled separately. This made it much less likely that completed measurements would be lost if a long run was interrupted.

For selection, I originally benchmarked select[a>=0](R), which caused every tuple to be copied into the output. This made the timing much larger because duplicate checking and result construction were included. I changed the benchmark to select[a<0](R). Every input tuple is still examined, so the selection counter remains correct, but no result tuples are inserted. This gives a cleaner measurement of the selection scan.

The select and project measurements were approximately linear, while the join measurements were approximately quadratic. The log-log slopes were about 1.00 for select, 1.00 for project, and 2.04 for join.

I also varied the join match rate at 4,000 tuples per relation. Every run still performed 16,000,000 comparisons, while runtime increased as the result size increased. This confirmed that the nested-loop algorithm always checks every pair regardless of how many pairs actually match.

## Session 7 - Final Review September 30th, 2026 

I finished the required tests, performance experiments, grammar document, report, README, and design log.

The main AI mistakes or incomplete suggestions that I had to identify and correct during the project were:

1. Treating relational keywords as permanently reserved tokens instead of allowing contextual identifiers.
2. Changing or losing attribute relation qualifiers when copying schemas.
3. Incorrect qualified attribute lookup in joins and self-joins.
4. Suggesting an impractical benchmark workflow before checking the growth rate of the nested-loop implementation.
5. Using a selection benchmark that included large result-construction costs instead of isolating the tuple scan.

These issues were found through required test cases, failed semantic behaviour, and performance measurements rather than accepting generated code without checking it.
---

## Project 2 — M1 checkpoint, November 15, 2026

### Reusing Bonus Project 1

I preserved all the existing Bonus 1 tests and made the storage engine a new package. The baseline was **32 passing tests**, and the combined suite now also tests M1 record/page encoding, heap operations, persistence, counters, CLI, condition parsing and tree serialization. `Relation` has an opt-in bag mode so M2/M3 can retain SQL duplicates while the legacy Bonus 1 set tests still pass.

### Decision: don't compact deleted slots

The assignment allows leaving tombstoned bytes in place. I chose no compaction for M1 because it makes RIDs stable and matches the required example after deleting slot 1. I explicitly track *contiguous usable free space* rather than guessing that a deleted record makes free bytes available.

### AI-assisted issue 1: storage API without a graded command-line interface

An initial development pass provided disk, slotted-page, directory, and buffer classes, but did not provide the five required `storage` commands. Inspection against Section 7 of the M1 PDF caught the omission. I added `storage.py`, a Windows launcher, argument validation, JSON outputs, and subprocess tests invoking commands exactly as a grader would.

### AI-assisted issue 2: two buffer pools alive together

An early `load` path held a catalog buffer pool in memory while a heap buffer pool was also running. Each pool could allocate B frames, potentially violating the global `--frames B` rule even though each individual pool respected B. A contract review found this. I changed the command flow to close and release catalog frames before opening heap frames, then reopened the catalog to update its metadata. The relevant test runs a heap scan at `B=2` and checks all pins are released afterward.

### AI-assisted issue 3: unintended duplicate removal

Bonus 1's set-based `Relation.add_tuple()` automatically drops duplicate rows, which would silently break SQL bag semantics if reused without modification. Reviewing the Bonus 2 week-one requirements exposed this behavior. I added an opt-in `bag=True` relation mode, propagated it through projection and rename, and verified projected duplicates remain present until `.distinct()` is explicitly requested. The legacy 32 tests still pass in set mode. This is a **compatibility bridge**, not a claim that the entire future executor is already bag-correct.

### Verified test results and outstanding work

- The instructor's 13/20/13-byte page example is exact; deleting slot 1 retains 4030 free bytes and leaves `(0,0)`.
- The provided B=3 buffer trace is exact: LRU (1,5,2), CLOCK (2,4,1) for hits/misses/evictions.
- A full CLI test creates a table, loads a quoted-comma CSV, scans with B=2, reproduces JSON deterministically, and displays page layout.
- Measured page capacities and cold 500-data-page scan are recorded in `REPORT_M1.md`.
- Official five Brightspace traces were not supplied; synthetic trace measurements are labeled as such. This is a remaining checkpoint requirement, not a completed one.
- Bonus 1 refactor remains partial: the old in-memory evaluator is retained for compatibility; a fully source-independent pull-based executor belongs to subsequent M2 work.
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

The combined test suite initially passed 85 tests in the local environment. I ran 36 join-size/frame experiments, six external-sort trials and a 40% skew hash-join case. A B=4 external-sort trial processed 88 input pages, more than 20 times its four-frame budget. The skew test used the on-disk fallback for an oversized partition and returned the expected 6,520 matches.

The separate full plan JSON schema mentioned in the M2 PDF was not supplied, and the implementation has not been tested against it. Some I/O counts are higher than ideal textbook costs because of temporary-file staging, and a global peak-frame monitor remains unimplemented. These limits are stated in the design and report rather than treated as passing requirements.

### Submission audit: intermediate REAL values

An additional regression test found that sorting the output of `GROUP BY` with `AVG` failed. The M2 temporary-record writer reused the M1 INT/VARCHAR encoder, which cannot encode the intermediate REAL value returned by AVG. I added a distinct executor-only temporary encoding for REAL using an eight-byte little-endian float; on-disk Module 1 table schemas remain limited to INT and VARCHAR. The new tests cover grouping followed by sorting and hash-based duplicate removal. After the correction, the local suite passed **101 tests**. This is a verified issue encountered during the final audit, not a claim of compatibility with hidden instructor plans.

## Project 2 — Module 3: SQL Front End (implementation review) explained thoroghly in previous milestone releases

- Reviewed the Module 3 contract, especially canonical operator ordering, name resolution, the difference between comma joins and `JOIN ... ON`, and bag versus set semantics.
- Implemented the scanner and parser separately from catalog-dependent compilation, allowing parsing without an existing database.
- Verified the reference plans for basic filtering, aliased joins, comma joins, HAVING, self joins, subqueries and UNION modes.
- **AI-assisted correction 1:** An early implementation of the condition formatter could retain type-checking state across boolean `AND` / `OR` boundaries. The logic was changed to clear that state at boolean boundaries; the final required-case suite was rerun.
- **AI-assisted correction 2:** Initial statement handling treated parsed INSERT statements only as structures. A later review added schema/type validation against the catalog for INSERT values. This still does not execute INSERT; execution remains outside the Module 3 compiler contract.
- The required-case tests passed (15 cases); full local regression suite passed (116 total). Exact hidden JSON-schema compatibility and thorough nested-condition validation remain outstanding.

This section is a summary of the implementation work and test evidence. Dates should be added only where supported by the actual development history.

## Project 2 – Module 4: Query Optimizer

### Session 1 – Reviewing the Optimizer Requirements
**Date:** Nov 12th ,2026

I started by reviewing the Module 4 requirements and comparing them with the work completed in Modules 2 and 3. The main goal was to take the logical plans generated by the SQL front end and turn them into physical plans that could be executed by Module 2.

One important part of the design was keeping the optimizer separate from the SQL parser and execution engine. Each module has its own responsibility, and the optimizer should decide how to run a query without changing what the query is supposed to return.

I also reviewed the required statistics, cost formulas, and rewrite rules before beginning the implementation.

### Session 2 – Statistics Collection and Catalog
**Date:** Nov 12th ,2026

I worked on implementing the ANALYZE command to collect information about tables and their columns.

The statistics included the number of records, number of data pages, average record size, distinct values, minimum and maximum values, and histogram information.

I used the existing Module 1 catalog as a starting point for storing the statistics.

One problem I found was that the catalog's page count did not always reflect the actual number of pages after records had been inserted through the heap file.

After testing this, I changed the statistics collection to count the actual data pages using the heap-file directory entries. This corrected the page-count results for the test database.

### Session 3 – Selectivity Estimation and Cost Formulas
**Date:** Nov 14th ,2026

The next part was estimating how many records would remain after different query operations.

I implemented selectivity calculations for equality comparisons, range conditions, AND, OR, and join conditions.

These estimates are used to predict the number of output rows and the number of pages needed for later operations.

I also implemented the I/O cost formulas for sorting and the three join algorithms.

An issue came up while checking the external-sort cost formula. An earlier version adjusted small buffer sizes to four frames, which caused the calculation for the instructor's three-frame example to be incorrect.

I removed that adjustment and added a regression test to verify the correct formula.

### Session 4 – Query Rewrite Rules
**Date:** Nov 14th ,2026

I worked on the logical-plan rewrite stage, which improves the query plan before choosing physical algorithms.

Some of the important rules included splitting conditions joined by AND, pushing filters closer to the tables they reference, and converting a cross product followed by an equality condition into a join.

The main challenge was making sure the rewrites did not change the meaning of the query.

For example, a filter referencing only one table can be pushed below a join, but a condition involving columns from both tables cannot be moved to only one side.

I also reviewed GROUP BY and HAVING because moving aggregate conditions before grouping could produce incorrect results.

### Session 5 – Join Ordering and Dynamic Programming
**Date:** Nov 14th ,2026

After implementing the rewrite stage, I worked on choosing an efficient join order.

Instead of always joining tables in the order written in the SQL query, the optimizer uses dynamic programming to compare different possible orders.

I used left-deep join trees to limit the number of combinations that needed to be considered.

The optimizer compares block nested-loop joins, sort-merge joins, and hash joins based on their estimated I/O costs and the available memory.

I also added a command to display the dynamic-programming table so the selected join order and its estimated cost could be reviewed.

### Session 6 – Module Integration and Debugging
**Date:** Nov 15th ,2026

One of the more challenging parts was making sure the physical plans generated by Module 4 worked directly with the Module 2 execution engine.

During testing, I found that Module 3 could generate rename operations for table aliases, but Module 2 did not initially support those operations.

I added rename handling to the executor and checked that the resulting plan could run without manual changes.

Another problem involved grouped queries using aggregate aliases, such as COUNT(*) AS n. The HAVING condition needed to recognize the aggregate output name.

I adjusted the lookup logic and tested the query again.

I also reviewed ORDER BY handling when the sorting column was not included in the final SELECT output. The plan needed to sort the records before removing that column.

These issues showed why testing each module separately was not enough to guarantee that the complete system would work correctly.

### Session 7 – Testing and Verification
**Date:** November 16, 2026

After implementing the main optimizer components, I ran the existing project tests along with the new Module 4 tests.

The combined local test suite passed **129 tests**.

I also tested the command-line tools for collecting statistics, generating physical plans, explaining estimated costs, and displaying dynamic-programming tables.

An end-to-end test was performed by compiling SQL into a logical plan, optimizing it, and passing the physical plan to Module 2 for execution.

The test returned the expected result without requiring manual changes to the generated plan.

I also used a synthetic four-table query to test dynamic-programming join enumeration.

Although these tests covered the main functionality, they did not guarantee that every hidden instructor test would pass.

### Session 8 – Documentation and Final Review
**Date:** Nov 15th ,2026

For the final review, I organized the Module 4 documentation and checked it against the assignment requirements.

The design document explains the statistics format, selectivity formulas, rewrite rules, cost calculations, and dynamic-programming approach.

The report includes the measurements that were completed, along with explanations of the assumptions used by the optimizer.

The official twenty-query workload and correlated dataset were not available during implementation, so the complete q-error analysis, optimizer comparison, rewrite-rule experiments, and correlated-data analysis were not finished.

I kept the synthetic measurements separate from the official workload requirements rather than presenting them as completed results.

Overall, the biggest lesson from Module 4 was that producing a valid physical plan is only part of query optimization. The optimizer also depends on reliable statistics and reasonable estimates.

Even when a query returns the correct result, inaccurate assumptions about the data can lead to an inefficient execution plan.

The next step is the integration checkpoint, where all four modules will be tested together as one database system.
