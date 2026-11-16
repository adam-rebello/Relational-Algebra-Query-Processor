"""COMP 3005 Module 4 optimizer CLI."""
import argparse
import json
import sys
from query_optimizer.core import Optimizer, OptimizerError, analyze

def main(argv=None):
    ap=argparse.ArgumentParser(description='Module 4 query optimizer')
    sub=ap.add_subparsers(dest='cmd',required=True)
    for name in ('analyze','plan','explain','dp-table'):
        p=sub.add_parser(name);p.add_argument('--db',required=True)
        if name=='analyze':
            p.add_argument('--table',required=True);p.add_argument('--buckets',type=int,default=20)
            p.add_argument('--frames',type=int,default=8)
        else:
            p.add_argument('--logical',required=True);p.add_argument('--frames',type=int,default=32)
            if name=='plan':p.add_argument('--json',action='store_true')
    a=ap.parse_args(argv)
    try:
        if a.cmd=='analyze':
            result=analyze(a.db,a.table,a.buckets,a.frames)
            print(json.dumps(result,indent=2))
            return 0
        with open(a.logical,encoding='utf-8') as f:logical=json.load(f)
        if not isinstance(logical,dict):raise OptimizerError('logical plan must be a single JSON object')
        opt=Optimizer(a.db,a.frames)
        if a.cmd=='plan':print(json.dumps(opt.plan(logical),indent=None if a.json else 2))
        elif a.cmd=='explain':print(opt.explain(logical))
        else:
            for row in opt.dp_table(logical):
                print(','.join(row['subset']),row['order'],row['algorithm'],
                      f"cost={row['cost']}",f"rows={row['rows']}",f"pages={row['pages']}")
        return 0
    except (OSError,ValueError,OptimizerError,KeyError,TypeError,json.JSONDecodeError) as e:
        print(f'error: {e}',file=sys.stderr)
        return 1

if __name__=='__main__':sys.exit(main())
