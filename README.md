# Relational Algebra Query Processor

COMP 3005 Bonus Project 1

This project implements a small relational algebra engine with a hand-written tokenizer, recursive descent parser, parse tree, and in-memory evaluator.

## Supported Operators

The engine supports:

- `select`
- `project`
- `rename`
- `union`
- `intersect`
- `minus`
- `times`
- `join`

Conditions support:

- `=`
- `!=`
- `<`
- `<=`
- `>`
- `>=`
- `not`
- `and`
- `or`

Attributes may be written normally, such as:

`Age`

or qualified with a relation name:

`Employees.Age`

## Requirements

Python 3.11 or later is recommended.

The test suite uses pytest.

Install pytest with:

`python -m pip install pytest`

## Running the Tests

Run all tests from the project root:

`python -m pytest -v`

The test suite includes all 25 required project cases along with additional tests.

## Printing a Parse Tree

Use the `--tree` option to print the parse tree without executing the query.

Example:

`python ra.py --tree "project[Name](select[Age>30](Employees))"`

Example output:

Project(attrs=[Name])
└── Select(cond=Compare(>))
    └── Relation(Employees)

The exact tree formatting may vary depending on the expression.

## Running a Query

Queries that require relation data use the `--data` option.

Example:

`python ra.py --data data/employees.ra "project[Name](select[Age>30](Employees))"`

An example relation file is:

Employees (EID, Name, Age, DID) = {
E1, John, 32, D1
E2, Alice, 28, D2
E3, Bob, 29, D1
}

## Relation Semantics

Relations use set semantics.

Duplicate tuples are removed using the project's own tuple equality logic rather than built-in set deduplication.

Projection also removes duplicate tuples after selecting the requested attributes.

## Join Semantics

The join operator is a theta join.

For example:

`Emp join[Emp.DID=Dept.DID] Dept`

The implementation uses nested loops and compares every tuple from the left relation with every tuple from the right relation.

This is intentionally not optimized with indexes, hash joins, or sort-merge joins because those are outside the scope of this project.

## Rename and Self Joins

The `rename` operator changes the relation name while keeping the same attributes and tuples.

Example:

`rename[E2](Emp)`

This allows self joins such as:

`rename[E2](Emp) join[Emp.MgrID=E2.EID] Emp`

Without rename, the two copies of `Emp` would not have distinguishable qualified attribute names.

## Error Handling

The engine supports the required error categories:

- lexical errors
- syntax errors
- name errors
- schema errors
- type errors

Errors are reported as readable messages instead of Python stack traces.

## Performance Testing

The join and select operators contain counters used for the performance study.

The join counter increments once for every pair of tuples whose join condition is evaluated.

The select counter increments once for every tuple examined.

The benchmark program is located in:

`tools/benchmark.py`

Run it from the project root with:

`python -m tools.benchmark`

The data generator is located in:

`tools/generate_data.py`

## Project Structure

- `GRAMMAR.md` - EBNF grammar, precedence, ambiguity example, and parser design
- `REPORT.md` - performance study and analysis
- `DESIGN_LOG.md` - development notes and problems encountered
- `README.md` - project instructions and overview
- `ra.py` - command-line entry point
- `src/` - tokenizer, parser, AST, evaluator, relation model, errors, and loader
- `tests/` - required and additional tests
- `tools/` - performance testing and data generation
- `data/` - example relation data

## Known Limitations

The project does not support NULL values or three-valued logic.

All relations are stored in memory.

Query optimization and algebraic rewriting are not implemented.

Indexes are not implemented.

Hash joins and sort-merge joins are not implemented.

The join operator uses nested loops and therefore becomes slow for large input relations.
---

# Project 2 — Module 1: Storage Engine and Buffer Pool

The original Bonus Project 1 implementation is preserved. M1 is implemented as a separate package in `storage_engine/` and a standalone `storage.py` command line tool. **Python 3.11+** is recommended; M1 has no third-party runtime dependencies. Tests require pytest.

## Quick start (Windows PowerShell)

Run commands from the project root:

```powershell
py storage.py create-table --db demo_db --name R --schema "a:INT,b:VARCHAR(20),c:INT"
py storage.py load --db demo_db --table R --file examples/m1_example.csv
py storage.py scan --db demo_db --table R --frames 8 --json
py storage.py layout --db demo_db --table R --page 1
py storage.py trace --file examples/trace_worked.txt --frames 3 --policy lru --json
py storage.py trace --file examples/trace_worked.txt --frames 3 --policy clock --json
```

Or use `storage.bat` on Windows. On macOS/Linux run `python3 storage.py ...` or `./storage ...`.

**Expected trace results:** LRU `hits=1, misses=5, evictions=2, reads=5, writes=0`; CLOCK `hits=2, misses=4, evictions=1, reads=4, writes=0`.

## Tests and measurements

```powershell
py -m pip install pytest
py -m pytest -q
$env:PYTHONPATH = "."
py tools/measure_m1.py
```

On macOS/Linux: `PYTHONPATH=. python3 tools/measure_m1.py`.

- `DESIGN_M1.md`: physical page formats, record encoding, free space, catalog, buffer policies and real byte-level example.
- `REPORT_M1.md`: measured capacities, replacement policies and 500-page scans.
- `measurements_m1/`: reproducible CSV data; **policy input sequences are generated stand-ins, not the official five Brightspace traces**.
- `tests/test_storage_engine.py` and `tests/test_refactor_m1.py`: M1 contract, CLI, and Bonus 1 compatibility tests.
- `src/tree_json.py`, `src/condition_api.py`: initial reusable Bonus 1 AST/condition helpers for future modules.

To test instructor trace inputs, run:

```powershell
py storage.py trace --file path/to/official_trace.txt --frames 16 --policy clock --json
```

**Known scope:** This checkpoint is M1 only; no SQL compiler, query optimizer, or external-sort executor is claimed. The official trace files and their measured report rows still need to be added if required for your M1 submission.

---

# COMP 3005 Project 2 — Module 1: Storage Engine and Buffer Pool

The original relational-algebra processor remains available as `ra.py`. The new
`storage_engine/` package implements 4096-byte disk pages, record encoding,
slotted pages, heap-file directories, a persistent catalog, and LRU/CLOCK buffer
replacement. The standalone `storage` launcher is provided for Unix-like shells;
use `storage.bat` on Windows, or `python storage.py` on any supported platform.

## Module 1 quick start

Python 3.11+ is recommended. From the repository root:

```bash
python -m pip install pytest
python -m pytest -q
python storage.py create-table --db demo_db --name R --schema "a:INT,b:VARCHAR(20),c:INT"
python storage.py load --db demo_db --table R --file examples/m1_example.csv
python storage.py scan --db demo_db --table R --frames 8 --json
python storage.py layout --db demo_db --table R --page 1
python storage.py trace --db demo_db --file examples/trace_worked.txt --frames 3 --policy lru --json
python storage.py trace --db demo_db --file examples/trace_worked.txt --frames 3 --policy clock --json
```

`create-table` and `load` persist their data under the supplied database directory.
For trace mode the input is one page number per line. See `DESIGN_M1.md` for
on-disk layout and design decisions; `REPORT_M1.md` for capacity, policy, and
scan-cost measurements; and `DESIGN_LOG.md` for implementation decisions and
AI-assisted corrections.

**Trace-data caveat:** The five official Brightspace traces were not provided
with the Module 1 PDF. The report labels generated trace measurements as
synthetic, not as official results. Replace them with the instructor's files
before treating the policy comparison as complete.

## Running the measurements

```bash
python tools/measure_m1.py
```

This writes CSV results under `measurements_m1/`. Do not commit generated
`demo_db/` or other local database files.

## COMP 3005 Project 2 — Module 2: Execution Engine

The physical plan executor is `exec.py`. It reads JSON plan trees and returns
bag-valued rows with per-operator comparison and disk-I/O counters. Base tables
are read through the Module 1 heap-file API and temporary pages through the
Module 1 disk manager. The CLI streams its JSON output instead of retaining
all returned rows in memory.

Implemented operator names: `seqscan`, `filter`, `project`, `limit`, `sort`,
`distinct` (sort/hash), `group_by` (sort/hash), `nested_loop_join`,
`sort_merge_join`, `hash_join`, `union_all`, `union`, `intersect`, `except`.

### Windows / local quick start

From the repository root in PowerShell (Python 3.11+):

```powershell
py -m pip install pytest matplotlib
py -m pytest -q
py storage.py create-table --db demo_m2 --name R --schema "a:INT,b:INT"
py storage.py create-table --db demo_m2 --name S --schema "b:INT,c:INT"
py storage.py load --db demo_m2 --table R --file examples/m2_R.csv
py storage.py load --db demo_m2 --table S --file examples/m2_S.csv
py exec.py run --db demo_m2 --plan examples/m2_join_plan.json --frames 4 --json
py exec.py trace --db demo_m2 --plan examples/m2_join_plan.json --frames 4
```

When a database folder already contains tables, don't rerun create-table on
it; choose a new folder (e.g. `demo_m2_2`) for a fresh demonstration.

### Measurement and documentation

```powershell
py tools/measure_m2.py
py tools/plot_m2.py
```

The measurement script creates temporary databases and writes its actual
results under `measurements_m2/`; the plot script creates two PNG graphs.

`DESIGN_M2.md` explains the resource strategy, algorithms, and limitations;
`REPORT_M2.md` includes 36 recorded join trials, six external-sort trials,
and a 40%-skew hash join. The full official plan JSON schema and sample plans
referenced in the instructor's M2 handout were not supplied, so the complete
hidden-test compatibility of the plan parser remains unverified. The current
nested-loop join stages inputs on disk and consequently has higher I/O than
the ideal textbook BNL formula. See the report for exact measured differences.

The project retains M1 and Bonus Project 1 code and regression tests. Module 3
(SQL front end) and Module 4 (optimizer) are separate future checkpoints.

### Module 2 submission audit

Run the complete regression suite from the repository root:

```bash
python -m pytest -q
```

The local pre-submission run reported 101 passing tests, including the
`tests/test_m2_submission_audit.py` checks. The Module 2 measurement data
are in `measurements_m2/`, and the tested implementation and limitations
are explained in `DESIGN_M2.md` and `REPORT_M2.md`. The executor supports
intermediate AVG results through a temporary REAL representation without
changing Module 1's INT/VARCHAR record format.

## Project 2 — Module 3 SQL front end

Module 3 adds a hand-written SQL lexer, parser, name resolver and logical-plan translator. It uses the Module 1 catalog, does not require Module 4, and does not run SQL statements. See `GRAMMAR_SQL.md`, `DESIGN_M3.md`, and `M3_AUDIT.md`.

On Windows use `python sql.py`, or `sql.bat`. On macOS/Linux use `python3 sql.py` or `./sql`.

```sh
python sql.py parse --query "SELECT name, age FROM Emp WHERE age > 30" --explain
python sql.py compile --db ./my_db --file query.sql --json
python sql.py check --db ./my_db --file query.sql
python -m pytest tests/test_module3.py -q
```

`compile` and `check` need existing tables in a Module 1 catalog at `./my_db`. The commands print `error: category: ... at line ..., column ...` and exit nonzero on failure.
