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
