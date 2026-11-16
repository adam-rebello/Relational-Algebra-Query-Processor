"""Minimal end-to-end tests of the integrated project shell."""
import io
import pytest
from db_shell import DatabaseShell, ShellError, split_statements


def test_sql_pipeline(tmp_path):
    out = io.StringIO()
    shell = DatabaseShell(tmp_path, frames=4, output=out)
    shell.run('CREATE TABLE R (id INT, tag VARCHAR(10))')
    shell.run("INSERT INTO R VALUES (1, 'one')")
    shell.run("INSERT INTO R VALUES (2, 'two')")
    assert shell.run('SELECT tag FROM R WHERE id > 1')['rows'] == 1
    shell.run('ANALYZE R')
    assert shell.run('EXPLAIN SELECT id FROM R') is None
    assert shell.run('EXPLAIN ANALYZE SELECT id FROM R')['rows'] == 2
    shell.run('SET frames = 8')
    assert shell.frames == 8
    assert 'Actual per-operator counts' in out.getvalue()


def test_join_and_load(tmp_path):
    out = io.StringIO()
    shell = DatabaseShell(tmp_path, output=out)
    shell.run('CREATE TABLE A (key INT, val VARCHAR(12))')
    shell.run('CREATE TABLE B (key INT, val VARCHAR(12))')
    file = tmp_path / 'a.csv'
    file.write_text('1,x\n2,y\n2,z\n', encoding='utf-8')
    shell.run(f"LOAD A FROM '{file}'")
    shell.run("INSERT INTO B VALUES (2, 'hello')")
    assert shell.run('SELECT a.val, b.val FROM A a JOIN B b ON a.key = b.key')['rows'] == 2
    assert shell.catalog()['A']['num_tuples'] == 3


def test_invalid_frames_and_semicolons(tmp_path):
    shell = DatabaseShell(tmp_path)
    with pytest.raises(ShellError):
        shell.run('SET frames = 3')
    statements, tail = split_statements("INSERT INTO T VALUES (1, 'a;b'); -- comment\nSELECT * FROM T;")
    assert len(statements) == 2 and not tail
    assert "'a;b'" in statements[0]
