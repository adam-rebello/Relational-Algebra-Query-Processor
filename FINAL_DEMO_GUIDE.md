# Final Integration Demonstration Guide

**Recommended video length:** approximately 8–12 minutes, or adjust to the professor's confirmed limit. The specification describes a 15-minute oral check; it does not itself require a self-recorded video.

## Preparation

1. Open the GitHub repository with all four module checkpoints tagged.
2. Open a terminal in the project folder and have the following commands ready.
3. Use a *fresh* demo database for the setup script to avoid duplicate-table errors.
4. Never display passwords or private files in the recording.

## Demo sequence and talking points

### Part 1 — Structure (about 1 minute)

Show `README.md`, `ARCHITECTURE.md`, and the folders `storage_engine`, `execution_engine`, `sql_frontend`, and `query_optimizer`.

Say: "The database has four independently testable modules. The SQL front end produces a logical JSON plan, the optimizer chooses a physical plan, the executor runs iterators, and the storage engine reads 4096-byte pages through its buffer pool."

### Part 2 — Storage and CRUD-like operations (about 2 minutes)

In a clean terminal, run:

```bash
python db_shell.py --db final_demo_db --frames 8 --file examples/integration_demo.sql
```

Show CREATE TABLE, INSERT, SELECT, ANALYZE, EXPLAIN, EXPLAIN ANALYZE and SET frames results. Explain that source tables live in heap files and their schemas in the catalog.

### Part 3 — JOIN (about 2 minutes)

Run:

```bash
python db_shell.py --db final_demo_db --frames 4 --file examples/integration_join_demo.sql
```

Point out the correct two output rows from an aliased join and the counters shown for EXPLAIN ANALYZE.

### Part 4 — Individual module contracts (about 2 minutes)

Briefly show the independent CLI commands:

```bash
python storage.py --help
python exec.py --help
python sql.py --help
python opt.py --help
```

If available, show the LRU/CLOCK worked trace and the DP table from the optimizer report. Be prepared to explain pinned pages, duplicate join keys, selection pushdown, and why a cost-based optimizer can make poor estimates when columns are correlated.

### Part 5 — Testing and report (about 2 minutes)

Show the test command:

```bash
python -m pytest -q
```

Point to `DESIGN_M1.md` through `DESIGN_M4.md`, `REPORT_M1.md` through `REPORT_M4.md`, and `DESIGN_LOG.md`. State precisely which measurements were synthetic and which official workloads were unavailable.

### Part 6 — Wrap-up (under 1 minute)

Say: "The integrated shell accepts SQL, builds logical and physical plans, executes them over disk-backed tables, and reports rows, page I/O and runtime. The four standalone module tools still work. The instructor's unseen dataset and PostgreSQL comparison remain a separate validation step."

## Avoid common demo issues

- Do not rerun CREATE TABLE on an existing demo database. Delete *only your disposable demo folder* or choose a new one.
- If you are on Windows, use `py` instead of `python` if that is how Python is installed.
- Run the demo SQL scripts from the project root so relative paths are correct.
- Record a real run; don't substitute pre-recorded output for an unsuccessful execution.
- A successful local test suite does not guarantee hidden-test completeness.
