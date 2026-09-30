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