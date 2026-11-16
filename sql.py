"""Module 3 SQL CLI: parse, compile, and check."""
import argparse
import json
import sys
from sql_frontend.compiler import Parser,Compiler,SQLError
from storage_engine.core import Catalog

def main(argv=None):
    p=argparse.ArgumentParser(description='COMP 3005 Module 3 SQL front end')
    sub=p.add_subparsers(dest='command',required=True)
    pa=sub.add_parser('parse');pa.add_argument('--query',required=True);pa.add_argument('--explain',action='store_true')
    for cmd in ('compile','check'):
        s=sub.add_parser(cmd);s.add_argument('--db',required=True);s.add_argument('--file',required=True)
        if cmd=='compile':s.add_argument('--json',action='store_true')
    args=p.parse_args(argv)
    try:
        if args.command=='parse':
            ast=Parser(args.query).parse()
            print(json.dumps(ast,indent=2,default=lambda x:[t.val for t in x] if isinstance(x,list) else str(x)))
            return 0
        with open(args.file,encoding='utf-8') as f:ast=Parser(f.read()).parse()
        cat=Catalog(args.db)
        try:data=cat.list_tables()
        finally:cat.close()
        plans=Compiler(data).compile(ast)
        if args.command=='compile':print(json.dumps(plans,indent=None if args.json else 2))
        return 0
    except (SQLError,OSError,ValueError) as e:
        print(str(e) if isinstance(e,SQLError) else f'error: schema: {e} at line 1, column 1',file=sys.stderr)
        return 1
if __name__=='__main__':sys.exit(main())
