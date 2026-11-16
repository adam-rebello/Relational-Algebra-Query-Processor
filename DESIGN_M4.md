# COMP 3005 Project 2 — Module 4 Design

## Purpose and integration

`opt.py` takes a Module 3 logical plan and returns a Module 2 physical plan. It does not execute tuples. It uses the Module 1 catalog and heap files, and Module 2's external sort for ANALYZE. M2 was extended with a pipelined `rename` operator and support for explicitly named aggregate output columns, so plans with SQL aliases and `GROUP BY ... AS ...` can be executed without editing the JSON.

## Catalog statistics and layout

`opt analyze --db DIR --table T --buckets k` scans the heap once into a bounded temporary page file and uses M2's external sorter to sort each column independently. Statistics are exact (no sampling): live row count, data-page count obtained by traversing heap directory pages, mean encoded record width, and per-column NDV, minimum, maximum and equi-depth histogram. Histogram bucket entries contain `min`, `max`, `count`, `ndv`. Duplicate key values may cross bucket boundaries when a target bucket size is reached; NDV is recomputed within each bucket. Empty columns have empty histograms and NDV zero.

The catalog records a `stats_file` pointer and `stats_size`. The full statistics payload is serialized as compact, sorted-key JSON into 4096-byte pages in `_opt_stats_T.db`, using the Module 1 disk manager. This is an intentional catalog-extension design: a full collection of 20-bucket histograms for many VARCHAR columns would exceed the Module 1 catalog's 4088-byte record limit if written inline. The catalog remains the authoritative entry point; it points to statistics stored in separately paged files. Re-running ANALYZE on unchanged data does not append another catalog version.

**Limit:** ANALYZE stages the table to a temporary page file and then performs external sorting per column; this introduces extra disk I/O. At `--frames 4`, sorting uses the M2 bounded-memory implementation. Temporary files are removed after completion.

## Selectivity estimates

With statistics, `c=v` takes `bucket.count / (total_rows * bucket.ndv)` for the first containing bucket; absent a histogram it uses `1 / NDV`. `<` and `>` sum complete buckets plus a linear estimate within a boundary bucket. `<>` is one minus equality. For boolean conditions, conjunction multiplies selectivities, disjunction uses `p + q - pq`, and NOT uses `1 - p`. An equality join estimates `R_rows * S_rows / max(NDV(R.a),NDV(S.b))`. Non-equality and unknown predicates default to 0.1. Estimates are rounded up and bounded to at least one row, as required. Output page estimates use `ceil(rows * avg_width / 4096)`.

These statistics assume uniformity **within** a bucket, independence **between** predicates, and approximate independence of join columns. The assumptions can fail badly when columns are correlated or when there are many duplicate values at boundaries. Missing statistics use conservative defaults (1000 rows, roughly 20 pages, unknown predicate selectivity 0.1); the plan remains compilable.

## Rewrite rules and preconditions

The optimizer implements the following rules conservatively, because a wrong rewrite changes query results:

1. Split top-level AND into stacked selections, preserving parentheses and quoted text.
2. Move selections below joins/crosses only when all referenced qualified columns are from one side.
3. Convert `select(R.a=S.a, cross(R,S))` into `join` only for a cross-side equality.
4. Move selections through a simple table rename by rewriting the qualifier, and through UNION / UNION ALL when their branch aliases are unambiguous.
5. Move a filter below `group_by` only when it references grouping columns (never aggregate results).
6. Add narrow projections at join leaves, keeping every qualified column used by the final projection or any join/filter predicate. It skips blocking operators.
7. Avoid removing semantic projections; redundant-projection and adjacent-selection cleanup are conservative rather than exhaustive.

**Known restriction:** The projection and selection rewrite logic is not complete for arbitrarily nested subqueries, grouping, and complex expressions. Rules are applied only when their preconditions can be established. Canonical operators are not shifted if doing so might change semantics.

## I/O cost model

All costs are estimated pages read plus pages written, ignoring CPU:

- seqscan: `M`
- filter/project/limit/rename: `0` additional I/O
- external sort: `2*M*(passes-1)+M`, where `passes=1+ceil(log_(B-1)(ceil(M/B)))` and single-run sorting has one pass
- nested loop: `M + ceil(M/(B-2))*N`
- sort-merge: `sort(M) + sort(N) + M + N`
- Grace hash: `3*(M+N)`
- distinct/group_by: sort cost in the selected sort-based implementation

Costs represent the specified algorithms. Actual M2 I/O can be greater because M2 stages some inputs in extra temporary files; comparisons in `REPORT_M2.md` document those differences.

## Left-deep dynamic programming

Connected join trees with two to six relations are flattened into base table references and join predicates. For each singleton subset the best plan is its access path. For each larger subset `S`, each possible rightmost relation `r` is considered, paired with the previously cheapest plan for `S-r`, and candidate block-nested-loop, sort-merge and Grace hash joins are costed. Sort-merge and hash are considered only for equality joins. Unconnected subsets are skipped when connected alternatives exist. The cheapest candidate is retained for each subset. Tie breaks are deterministic. The `dp-table` command prints the best entry for each reachable subset; one four-relation example is saved as `measurements_m4/four_table_dp.json`.

Left-deep trees allow tuple pipelining of the outer input and reduce the search space from all possible binary trees. This rules out some bushy plans, which can be cheaper when independently reduced subtrees would otherwise join early. Disconnected or unsupported join-tree shapes use a limited fallback rather than claiming exhaustive enumeration.

## Physical plan contract

Logical `scan` maps to `seqscan`; `select` to `filter`; `join` to one of the three physical joins; `distinct` and `group_by` specify `mode='sort'`; `limit.count` maps to `limit.n`. Logical rename is kept as a pipelined physical rename. All generated plans use the exact Module 2 field names and are validated by the Module 2 builder in the integration tests.

## Verification

The optimizer tests cover ANALYZE repeatability, real heap page counts, cost formulas, predicate pushdown, the comma/equijoin equivalence, four-relation DP enumeration, COUNT aliases, self-joins, SELECT DISTINCT, UNION ALL, LIMIT and sorting on a non-projected column. See `tests/test_module4.py`. The complete legacy plus M1–M4 local regression suite passes; this is not a claim of passing hidden instructor tests.

## Relevant reading / design influence

- Selinger et al., *Access Path Selection in a Relational Database Management System* (SIGMOD 1979): motivated the subset-based left-deep join-order dynamic programming.
- Ramakrishnan and Gehrke, *Database Management Systems*, optimizer material (chapter 15 in the assignment's reading list): motivated page-I/O costing, histogram-based selectivity and pushdown.

The exact formulas and required CLI contracts above follow the instructor's Module 4 specification rather than substitutions from general reference texts.
