"""Repeatable SYNTHETIC smoke measurements, not the official 20-query workload."""
import csv
import json
import tempfile
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from storage_engine.core import Catalog,HeapFile
from sql_frontend.compiler import Parser,Compiler
from query_optimizer.core import Optimizer,analyze
from execution_engine.core import build,nodes

def run(db,plan,B):
    root=build(plan,db,B);n=0
    try:
        root.open()
        while root.next() is not None:n+=1
    finally:root.close()
    counters={key:sum(nd.counters()[key] for _,nd in nodes(root)) for key in ('page_reads','page_writes')}
    return n,counters['page_reads']+counters['page_writes']

def main():
    output=Path(__file__).resolve().parents[1]/'measurements_m4'
    output.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as db:
        schema=[['id','INT'],['k','INT'],['v','INT']]
        cat=Catalog(db)
        for t in ['A','B','C','D']:cat.create_table(t,schema)
        cat.close()
        for i,t in enumerate(['A','B','C','D']):
            heap=HeapFile(Path(db)/(t+'.db'),schema,4)
            for j in range([140,90,70,50][i]):heap.insert([j,j%12,j%5])
            heap.close()
            analyze(db,t,4)
        cat=Catalog(db);metadata=cat.list_tables();cat.close()
        sql=[
            'SELECT a.id FROM A a JOIN B b ON a.k = b.k WHERE a.v > 2;',
            'SELECT a.id FROM A a, B b WHERE a.k = b.k AND b.v > 2;',
            'SELECT a.id FROM A a JOIN B b ON a.k = b.k JOIN C c ON b.k = c.k;',
            'SELECT a.id FROM A a JOIN B b ON a.k = b.k JOIN C c ON b.k = c.k JOIN D d ON c.k = d.k;'
        ]
        rows=[]
        for number,q in enumerate(sql,1):
            logical=Compiler(metadata).compile(Parser(q).parse())
            for B in (4,16):
                opt=Optimizer(db,B);physical=opt.plan(logical)
                count,cost=run(db,physical,B)
                estimated=opt._estimate_physical(physical)['rows']
                rows.append(dict(query=number,frames=B,estimated_rows=estimated,actual_rows=count,actual_io=cost,
                                 root_op=physical['op']))
                if number==4 and B==4:
                    with (output/'four_table_dp.json').open('w') as f:json.dump(opt.last_dp,f,indent=2)
                    with (output/'four_table_plan.json').open('w') as f:json.dump(physical,f,indent=2)
        with (output/'synthetic_workload.csv').open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
        print('SYNTHETIC measurement rows:',len(rows))
        print(json.dumps(rows,indent=2))
if __name__=='__main__':main()
