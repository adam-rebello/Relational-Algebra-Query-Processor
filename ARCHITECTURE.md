# COMP 3005 Project 2 — System Architecture

## Overview

The integrated shell connects the four independently runnable modules. SQL source text is parsed into a logical plan, the optimizer converts it into a physical plan, and the iterator executor requests rows from the on-disk storage engine. The original Module 1–4 command-line tools remain usable separately.

```text
SQL text / shell commands
         |
         v
M3 sql_frontend.compiler.Parser + Compiler
         |  logical plan JSON
         v
M4 query_optimizer.core.Optimizer
   statistics -> rewrites -> cardinality/cost -> join order/algorithm
         |  physical plan JSON
         v
M2 execution_engine.core.build -> open/next/close
         |  iterator tuple requests
         v
M1 storage_engine.core.HeapFile / Catalog / BufferPool / DiskManager
         |  4096-byte heap and catalog pages on disk
         v
 result rows + per-operator counters
```

## Contracts between modules

- **M3 to M4:** `Compiler(catalog).compile(Parser(text).parse())` returns a logical JSON-compatible node (`scan`, `project`, `select`, `join`, etc.) for a SELECT statement. It never selects a physical join algorithm.
- **M4 to M2:** `Optimizer(db, frames).plan(logical)` returns a physical JSON-compatible plan (`seqscan`, `filter`, `project`, one of the join algorithms, and the other physical operators). The shell passes the resulting object directly to `build` without rewriting its schema.
- **M2 to M1:** `build(plan, db, frames)` creates iterators. Scans use heap files through Module 1 buffer pools. Operators expose `open`, `next`, `close`, and `counters`.
- **Catalog:** M1 stores table schemas in `catalog.db`; M4's ANALYZE writes and reads statistics referenced from catalog metadata.

## Shell and lifecycle

Run `python db_shell.py --db demo_db --frames 8`. It supports the project SQL subset, including CREATE TABLE, INSERT INTO ... VALUES, SELECT, and the shell-level commands `ANALYZE table`, `SET frames = N`, `LOAD table FROM 'file.csv'`, `EXPLAIN <SELECT>`, and `EXPLAIN ANALYZE <SELECT>`. `--file script.sql` runs a batch script. `.tables`, `.help`, and `.quit` are convenience commands.

For each SELECT, the shell loads catalog metadata, compiles the SQL, asks M4 to select a physical plan, and pulls rows using `root.open()`, repeated `root.next()` and `root.close()` in a `finally` block. Results are streamed rather than accumulated into a list. The shell prints output tuple counts, the executor-reported read/write and comparison counts, and wall time. `EXPLAIN ANALYZE` prints estimated plan annotations and observed per-operator counters.

CREATE and INSERT write to the M1 heap and catalog. LOAD uses M1's heap insertions and a streaming CSV reader. ANALYZE calls the M4 statistics collector. Batch statement splitting respects single-quoted SQL strings and `--` comments.

## Memory and page accounting

Every storage page is 4096 bytes. The shell accepts `--frames B` and `SET frames = B` with B >= 4. It delegates actual page allocation, eviction, temporary-file accounting, and buffer limits to Modules 1 and 2. The integration layer itself does not materialize an entire query result. Root counters are summed from the executor operator tree after closure. Frame-budget enforcement is not independently instrumented at the shell layer; the executor's documented limitations still apply.

## Testing and limitations

The integrated demo tests CREATE/INSERT/SELECT, ANALYZE, EXPLAIN, EXPLAIN ANALYZE, LOAD, join aliases, and changing B. The complete local regression suite was 132 tests passing when this document was written. The separate 25-query hidden workload and its PostgreSQL comparison data were not supplied. `tools/integration_workload.py` can collect per-query result counts, root estimated rows, I/O and wall time when that workload becomes available, but it does not prove answer equivalence against PostgreSQL. Some operator-level memory/counter corner cases remain dependent on earlier module implementations.

## What I would change if starting again

I would define the shared schemas and frame-accounting interface before writing any physical operators, then maintain a permanent compatibility test for every module boundary. In particular, SELECT aliases, aggregate output types, and I/O ownership turned out to be easier to debug through small end-to-end fixtures than in isolated module tests. I would also arrange automatic cross-checking against PostgreSQL from the first integration iteration so cardinality and bag-semantics regressions are caught early.
