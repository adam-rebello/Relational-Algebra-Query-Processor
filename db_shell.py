"""Interactive SQL shell for COMP 3005 Project 2 integration.

Commands: CREATE TABLE, INSERT, SELECT, EXPLAIN, EXPLAIN ANALYZE,
ANALYZE table, SET frames = N, LOAD table FROM 'path', .tables, .help, .quit.

Four module boundaries are preserved: SQL -> logical JSON -> optimizer ->
physical JSON -> iterator executor -> buffered heap storage.
"""
import argparse
import csv
import json
import shlex
import sys
import time
from pathlib import Path

from sql_frontend.compiler import Parser, Compiler, SQLError
from query_optimizer.core import Optimizer, OptimizerError, analyze
from execution_engine.core import build, nodes, PlanError
from storage_engine.core import Catalog, HeapFile, StorageError


class ShellError(Exception):
    pass


class DatabaseShell:
    def __init__(self, db, frames=8, output=None):
        if frames < 4:
            raise ShellError('frame budget must be at least 4')
        self.db = Path(db)
        self.db.mkdir(parents=True, exist_ok=True)
        self.frames = frames
        self.output = output or sys.stdout

    def say(self, message=''):
        print(message, file=self.output)

    def catalog(self):
        cat = Catalog(self.db, min(self.frames, 4))
        try:
            return cat.list_tables()
        finally:
            cat.close()

    def set_frames(self, text):
        # SET frames = 8, with optional whitespace and case-insensitive keyword.
        parts = text.replace('=', ' = ').split()
        if len(parts) != 4 or parts[0].upper() != 'SET' or parts[1].lower() != 'frames' or parts[2] != '=':
            raise ShellError('expected SET frames = N')
        try:
            frames = int(parts[3])
        except ValueError as exc:
            raise ShellError('frame budget must be an integer') from exc
        if frames < 4:
            raise ShellError('frame budget must be at least 4')
        self.frames = frames
        self.say(f'frames = {frames}')

    def create(self, statement):
        name, schema = statement['name'], statement['schema']
        # Create the heap before publishing the catalog entry (same as M1 CLI).
        cat = Catalog(self.db, self.frames)
        try:
            if name in cat.list_tables() or (self.db / (name + '.db')).exists():
                raise ShellError(f'table already exists: {name}')
        finally:
            cat.close()
        heap = HeapFile(self.db / (name + '.db'), schema, self.frames)
        heap.close()
        cat = Catalog(self.db, self.frames)
        try:
            cat.create_table(name, schema)
        finally:
            cat.close()
        self.say(f'Created table {name}')

    def insert(self, statement):
        name = statement['table']
        cat = Catalog(self.db, self.frames)
        try:
            info = cat.get_table(name)
        finally:
            cat.close()
        # The SQL compiler validates number/types before calling this function.
        heap = HeapFile(self.db / info['file'], info['schema'], self.frames)
        try:
            heap.insert(statement['values'])
            page_count = heap.disk.num_pages()
        finally:
            heap.close()
        cat = Catalog(self.db, self.frames)
        try:
            cat.update_table(name, num_tuples=info['num_tuples'] + 1, num_pages=page_count)
        finally:
            cat.close()
        self.say('Inserted 1 row')

    def load(self, text):
        # Use shlex only for the shell-specific LOAD command, not SQL parsing.
        try:
            parts = shlex.split(text)
        except ValueError as exc:
            raise ShellError(str(exc)) from exc
        if len(parts) != 4 or parts[0].upper() != 'LOAD' or parts[2].upper() != 'FROM':
            raise ShellError("expected LOAD table FROM 'path.csv'")
        table, filepath = parts[1], Path(parts[3])
        cat = Catalog(self.db, self.frames)
        try:
            info = cat.get_table(table)
        finally:
            cat.close()
        count = 0
        heap = HeapFile(self.db / info['file'], info['schema'], self.frames)
        try:
            with filepath.open(newline='', encoding='utf-8-sig') as source:
                reader = csv.reader(source, strict=True)
                for row in reader:
                    try:
                        heap.insert(row)
                    except StorageError as exc:
                        raise ShellError(f'CSV line {reader.line_num}: {exc}') from exc
                    count += 1
            page_count = heap.disk.num_pages()
        finally:
            page_count = heap.disk.num_pages()
            heap.close()
            # A failed CSV load may have inserted earlier valid rows. Persist
            # their actual count even when a later row raises an error.
            cat = Catalog(self.db, self.frames)
            try:
                cat.update_table(table, num_tuples=info['num_tuples'] + count,
                                 num_pages=page_count)
            finally:
                cat.close()
        self.say(f'Loaded {count} rows into {table}')

    def execute_plan(self, physical, show_rows=True):
        root = build(physical, str(self.db), self.frames)
        started = time.perf_counter()
        count = 0
        try:
            root.open()
            if show_rows:
                self.say(' | '.join(c[0] for c in root.schema))
            while True:
                row = root.next()
                if row is None:
                    break
                if show_rows:
                    self.say(' | '.join(str(v) for v in row))
                count += 1
        finally:
            root.close()
        elapsed = time.perf_counter() - started
        stats = list(nodes(root))
        totals = {name: sum(op.counters()[name] for _, op in stats)
                  for name in ('comparisons', 'page_reads', 'page_writes')}
        totals['tuples_out'] = count
        self.say(f'{count} row(s) | reads={totals["page_reads"]} writes={totals["page_writes"]} '
                 f'comparisons={totals["comparisons"]} elapsed={elapsed:.4f}s')
        return {'rows': count, 'totals': totals, 'elapsed': elapsed,
                'operators': [(depth, op.name, op.counters()) for depth, op in stats]}

    def run(self, sql):
        text = sql.strip().rstrip(';').strip()
        if not text:
            return None
        upper = text.upper()
        if upper in ('.QUIT', '.EXIT', 'QUIT', 'EXIT'):
            return 'exit'
        if upper in ('.HELP', 'HELP'):
            self.say('CREATE TABLE / INSERT / SELECT / EXPLAIN / EXPLAIN ANALYZE / ANALYZE table /')
            self.say("SET frames = N / LOAD table FROM 'file.csv' / .tables / .quit")
            return None
        if upper == '.TABLES':
            for table in self.catalog():
                self.say(table)
            return None
        if upper.startswith('SET '):
            self.set_frames(text)
            return None
        if upper.startswith('LOAD '):
            self.load(text)
            return None
        if upper.startswith('ANALYZE '):
            args = text.split()
            if len(args) != 2:
                raise ShellError('expected ANALYZE table')
            result = analyze(str(self.db), args[1], frames=self.frames)
            self.say(f'Analyzed {args[1]}: {result["n_tuples"]} rows, {result["n_pages"]} pages')
            return result

        explain = upper.startswith('EXPLAIN ')
        explain_analyze = upper.startswith('EXPLAIN ANALYZE ')
        query_text = text[16:].strip() if explain_analyze else text[8:].strip() if explain else text
        ast = Parser(query_text).parse()
        logical = Compiler(self.catalog()).compile(ast)
        if isinstance(logical, list):
            # Multiple statements passed as one string are handled in order.
            results = []
            for stmt in ast:
                # Recompile separately so CREATE becomes visible to next statements.
                results.append(self.run_ast(stmt))
            return results
        if logical.get('kind') == 'create':
            self.create(logical)
            return None
        if logical.get('kind') == 'insert':
            self.insert(logical)
            return None
        if explain:
            optimizer = Optimizer(str(self.db), self.frames)
            self.say(optimizer.explain(logical))
            if not explain_analyze:
                return None
        physical = Optimizer(str(self.db), self.frames).plan(logical)
        result = self.execute_plan(physical, show_rows=not explain_analyze)
        if explain_analyze:
            self.say('Actual per-operator counts:')
            for depth, name, counts in result['operators']:
                self.say('  ' * depth + f'{name}: rows={counts["tuples_out"]}, '
                         f'reads={counts["page_reads"]}, writes={counts["page_writes"]}')
        return result

    def run_ast(self, statement):
        # Use the most up-to-date catalog, including tables created earlier in a file.
        compiled = Compiler(self.catalog()).compile([statement])
        kind = compiled.get('kind')
        if kind == 'create':
            return self.create(compiled)
        if kind == 'insert':
            return self.insert(compiled)
        return self.execute_plan(Optimizer(str(self.db), self.frames).plan(compiled))


def split_statements(text):
    """Split on SQL semicolons outside quoted strings and -- comments."""
    result = []
    current = []
    quoted = False
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "'":
            current.append(ch)
            if quoted and i + 1 < len(text) and text[i + 1] == "'":
                current.append("'")
                i += 2
                continue
            quoted = not quoted
        elif not quoted and text.startswith('--', i):
            while i < len(text) and text[i] != '\n':
                i += 1
            continue
        elif ch == ';' and not quoted:
            statement = ''.join(current).strip()
            if statement:
                result.append(statement)
            current = []
        else:
            current.append(ch)
        i += 1
    return result, ''.join(current).strip()


def main(argv=None):
    cli = argparse.ArgumentParser(description='COMP 3005 integrated SQL database shell')
    cli.add_argument('--db', required=True)
    cli.add_argument('--frames', type=int, default=8)
    cli.add_argument('--file', help='execute statements from a SQL file')
    options = cli.parse_args(argv)
    try:
        shell = DatabaseShell(options.db, options.frames)
        if options.file:
            text = Path(options.file).read_text(encoding='utf-8')
            statements, tail = split_statements(text)
            if tail:
                statements.append(tail)
            for stmt in statements:
                shell.run(stmt)
            return 0
        print('COMP 3005 DB shell — .help for commands, .quit to exit')
        pending = ''
        while True:
            try:
                line = input('db> ' if not pending else '... ')
            except EOFError:
                break
            if not pending and line.strip().lower() in ('.quit', '.exit', '.help', '.tables'):
                if shell.run(line) == 'exit':
                    break
                continue
            pending += line + '\n'
            statements, pending = split_statements(pending)
            for stmt in statements:
                try:
                    if shell.run(stmt) == 'exit':
                        return 0
                except (ShellError, SQLError, OptimizerError, PlanError,
                        StorageError, OSError, ValueError, KeyError, TypeError) as exc:
                    print('error:', exc, file=sys.stderr)
        return 0
    except (ShellError, SQLError, OptimizerError, PlanError,
            StorageError, OSError, ValueError, KeyError, TypeError) as exc:
        print('error:', exc, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
