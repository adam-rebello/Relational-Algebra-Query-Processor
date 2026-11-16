"""Module 2 physical plan runner.

Usage:
 python exec.py run --db dbdir --plan query.json --frames 4 --json
 python exec.py trace --db dbdir --plan query.json --frames 4

JSON output streams its rows; the CLI does not accumulate the full result.
"""
import argparse
import json
import sys
from execution_engine.core import PlanError, build, nodes
from storage_engine.core import StorageError

def main(argv=None):
    cli=argparse.ArgumentParser()
    sub=cli.add_subparsers(dest='cmd',required=True)
    for command in ('run','trace'):
        parser=sub.add_parser(command)
        parser.add_argument('--db',required=True)
        parser.add_argument('--plan',required=True)
        parser.add_argument('--frames',type=int,default=4)
        parser.add_argument('--json',action='store_true')
    args=cli.parse_args(argv)
    if args.frames<4:cli.error('Module 2 requires at least 4 frames')
    try:
        with open(args.plan,encoding='utf-8') as f:
            plan=json.load(f)
        root=build(plan,args.db,args.frames)
        if args.cmd=='run' and args.json:
            sys.stdout.write('{"schema":'+json.dumps(root.schema,ensure_ascii=False)+',"rows":[')
        count=0
        try:
            root.open()
            while True:
                row=root.next()
                if row is None:break
                if args.cmd=='run':
                    if args.json:
                        if count:sys.stdout.write(',')
                        sys.stdout.write(json.dumps(row,ensure_ascii=False))
                    else:print(*row,sep=' | ')
                count+=1
        finally:
            root.close()
        node_list=list(nodes(root))
        totals={key:sum(node.counters()[key] for _,node in node_list)
                for key in ('comparisons','page_reads','page_writes')}
        totals['tuples_out']=root.tuples_out
        if args.cmd=='run':
            if args.json:
                sys.stdout.write('],"totals":'+json.dumps(totals)+'}\n')
            else:print('totals:',totals)
        else:
            for depth,node in node_list:
                c=node.counters()
                print('  '*depth+f'{node.name} tuples_out={c["tuples_out"]} '
                      f'comparisons={c["comparisons"]} reads={c["page_reads"]} writes={c["page_writes"]}')
        return 0
    except (OSError,json.JSONDecodeError,PlanError,StorageError,ValueError,RuntimeError) as e:
        print(f'Error: {e}',file=sys.stderr)
        return 1

if __name__=='__main__':
    sys.exit(main())
