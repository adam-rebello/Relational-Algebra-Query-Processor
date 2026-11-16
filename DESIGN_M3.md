# COMP 3005 Project 2 — Module 3 Design

## Overview

`sql_frontend/compiler.py` contains three layers: a character-by-character tokenizer (`tokenize`), a hand-written recursive-descent statement parser (`Parser`), and a separate catalog-aware semantic analyzer/translator (`Compiler`). `sql.py` exposes the three commands. No regular expressions, parser generators or `eval` are used. The compiler does not execute SQL.

## Catalog, scope and resolution

`compile` and `check` open the Module 1 `Catalog` for the supplied `--db` folder and read table names and ordered column schemas. A table reference supplies one scope entry, keyed by an alias when present and otherwise its table name. A repeated entry name raises an error. For `t.c`, `t` must exist and `c` must occur in its schema. Unqualified `c` must occur in exactly one scope entry. Missing and ambiguous references raise different error categories; ambiguous names include candidate sources. `SELECT *` follows the original FROM and schema order, qualifying every column, including same-named columns from different tables.

A subquery is compiled on its own and its projected output names form the outer alias's schema. `ORDER BY` looks at projected aliases first, then the input scope, so a non-projected input column remains usable for ordering.

## SQL bags and duplicate elimination

A `scan` and `project` preserve duplicate tuples. A `SELECT` without DISTINCT never creates a distinct node. Explicit `SELECT DISTINCT` adds a `distinct` node above the projection unless grouping already makes it redundant. `UNION ALL` produces `union_all` and retains duplicates; `UNION` produces `union`. `INTERSECT` and `EXCEPT` are set operations. `group_by` forms one row per group, so a second deduplication is unnecessary. These are logical choices; physical algorithms belong in Modules 2 and 4.

## Aggregation and translation

The input tree is assembled in canonical bottom-to-top order: FROM / JOIN / CROSS, WHERE select, GROUP BY, HAVING select, PROJECT, DISTINCT (when needed), SORT, LIMIT, then set operations left to right. An explicit `JOIN ... ON` retains its predicate in the join node; a comma join forms `cross`, and its WHERE condition remains above the cross. No predicate pushdown occurs in Module 3.

A query with GROUP BY or an aggregate in SELECT is aggregating. Its nonaggregate selected columns must all be grouping columns. `SUM` and `AVG` accept INT only. Unnamed aggregates are named `count_star`, `avg_Emp_salary`, etc. An explicit AS alias overrides the name. HAVING uses the aggregate output alias where possible. Errors use `error: category: message at line L, column C` with categories listed in the specification.

## Limitations and contract risks

The implementation passed the 15 required-case tests, but they do not cover every SQL grammar combination. Specifically, nested boolean-expression validation, compound conditions with aggregates, aliases for ordinary projected columns, and the exact external full-plan JSON schema have not received exhaustive validation. `CREATE` and `INSERT` are parsed and represented as statement structures; this module is not a DDL/DML executor. It is not appropriate to claim hidden-test coverage or full M2 interoperability before testing the separately supplied logical-plan schema and examples.

## Interface and verification

- `python sql.py parse --query "SELECT ..." --explain`
- `python sql.py compile --db DIR --file query.sql --json`
- `python sql.py check --db DIR --file query.sql`
- `python -m pytest tests/test_module3.py -q`

The tests check self joins, star expansion, ambiguity, UNION modes, grouping/HAVING, invalid aggregate placement, subquery aliases, ordering on non-projected columns, type errors, unknown names, duplicate aliases, COUNT without grouping, mismatched set schemas, and four-table joins.
