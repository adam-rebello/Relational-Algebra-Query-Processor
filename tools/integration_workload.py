"""Run a supplied SQL workload and save root-level integration measurements.

Example: python tools/integration_workload.py --db db/ --file workload.sql --frames 8 --out results.csv
This does not substitute for comparing query answers with PostgreSQL.
"""
import argparse
import csv
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from db_shell import DatabaseShell, split_statements
from sql_frontend.compiler import Parser, Compiler
from query_optimizer.core import Optimizer


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', required=True)
    parser.add_argument('--file', required=True)
    parser.add_argument('--frames', type=int, default=8)
    parser.add_argument('--out', default='integration_results.csv')
    args = parser.parse_args()
    statements, tail = split_statements(Path(args.file).read_text(encoding='utf-8'))
    if tail:
        statements.append(tail)
    shell = DatabaseShell(args.db, args.frames, output=io.StringIO())
    results = []
    for number, sql in enumerate(statements, 1):
        row = {'query': number, 'sql': sql.replace('\n', ' '), 'status': 'ok'}
        try:
            if not sql.lstrip().upper().startswith('SELECT'):
                raise ValueError('workload runner accepts SELECT queries only')
            logical = Compiler(shell.catalog()).compile(Parser(sql).parse())
            optimizer = Optimizer(args.db, args.frames)
            physical = optimizer.plan(logical)
            estimate = optimizer._estimate_physical(physical)['rows']
            actual = shell.execute_plan(physical, show_rows=False)
            row.update(estimated_rows=estimate, actual_rows=actual['rows'],
                       page_reads=actual['totals']['page_reads'],
                       page_writes=actual['totals']['page_writes'],
                       wall_seconds=f'{actual["elapsed"]:.6f}')
        except Exception as exc:
            row['status'] = f'error: {exc}'
        results.append(row)
    columns = ['query', 'sql', 'status', 'estimated_rows', 'actual_rows',
               'page_reads', 'page_writes', 'wall_seconds']
    with open(args.out, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(results)
    print(f'Wrote {len(results)} query measurements to {args.out}')
    return 0 if all(r['status'] == 'ok' for r in results) else 1


if __name__ == '__main__':
    sys.exit(main())
