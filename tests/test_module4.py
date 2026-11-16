"""Module 4 focused contract checks on real Module 1 heap files."""
import json
from pathlib import Path
import pytest
from storage_engine.core import Catalog, HeapFile
from query_optimizer.core import Optimizer, analyze, rewrite, sort_cost, join_cost
from execution_engine.core import build
from sql_frontend.compiler import Parser, Compiler

@pytest.fixture
def db(tmp_path):
    tables={
        'Emp':([['did','INT'],['age','INT'],['name','VARCHAR',20]],[[1,40,'a'],[1,30,'b'],[2,70,'c'],[2,70,'c']]),
        'Dept':([['did','INT'],['budget','INT']],[[1,2000],[2,1000]]),
        'P':([['did','INT'],['pid','INT']],[[1,9],[2,10]]),
        'T':([['did','INT'],['tid','INT']],[[1,8],[2,7]])}
    cat=Catalog(tmp_path)
    for name,(schema,rows) in tables.items():cat.create_table(name,schema)
    cat.close()
    for name,(schema,rows) in tables.items():
        heap=HeapFile(tmp_path/(name+'.db'),schema,4)
        for row in rows:heap.insert(row)
        heap.close()
    return tmp_path

def compile_sql(db,text):
    cat=Catalog(db)
    try:info=cat.list_tables()
    finally:cat.close()
    return Compiler(info).compile(Parser(text).parse())

def execute(db,plan,frames=4):
    root=build(plan,db,frames)
    output=[]
    try:
        root.open()
        while True:
            row=root.next()
            if row is None:break
            output.append(row)
    finally:root.close()
    return output

def test_analyze_persistent_and_repeatable(db):
    a=analyze(db,'Emp',2); b=analyze(db,'Emp',2)
    assert a==b
    assert a['n_pages']==1 and a['n_tuples']==4
    assert a['columns']['did']['ndv']==2
    assert sum(x['count'] for x in a['columns']['did']['hist'])==4
    assert Optimizer(db).stats['Emp']==a

def test_selectivity_and_cost_formulas(db):
    analyze(db,'Emp',2)
    o=Optimizer(db,4)
    assert o.selectivity('Emp.did = 1')==pytest.approx(0.5)
    assert o.selectivity('Emp.did <> 1')==pytest.approx(0.5)
    assert join_cost('nested_loop_join',100,10,32)==140
    assert join_cost('hash_join',100,10,32)==330
    assert sort_cost(8,3)==40 # formula 2*M*(3-1)+M

def test_split_push_convert(db):
    p={'op':'select','condition':'Emp.did = Dept.did AND Emp.age > 30 AND Dept.budget > 1500',
       'child':{'op':'cross','left':{'op':'scan','table':'Emp'},'right':{'op':'scan','table':'Dept'}}}
    r=rewrite(p)
    assert r['op']=='join' and r['condition']=='Emp.did = Dept.did'
    assert r['left']['op']=='select' and r['right']['op']=='select'

def test_optimizer_compiler_executor_join(db):
    for t in ('Emp','Dept'):analyze(db,t,2)
    queries=[
        'SELECT e.name FROM Emp e JOIN Dept d ON e.did = d.did WHERE d.budget > 1500;',
        'SELECT e.name FROM Emp e, Dept d WHERE e.did = d.did AND d.budget > 1500;'
    ]
    plans=[]
    for sql in queries:
        logical=compile_sql(db,sql)
        physical=Optimizer(db,4).plan(logical)
        assert execute(db,physical)==[['a'],['b']]
        plans.append(physical)
    assert plans[0]==plans[1]

def test_four_relations_dp(db):
    for t in ('Emp','Dept','P','T'):analyze(db,t,2)
    q=compile_sql(db,'SELECT e.name FROM Emp e JOIN Dept d ON e.did = d.did JOIN P p ON p.did = d.did JOIN T t ON t.did = p.did;')
    o=Optimizer(db,4);p=o.plan(q)
    assert len(o.last_dp)>4
    assert len(execute(db,p))==4

def test_group_alias_through_optimizer(db):
    for t in ('Emp',):analyze(db,t,2)
    q=compile_sql(db,'SELECT did,COUNT(*) AS n FROM Emp GROUP BY did HAVING COUNT(*) > 1 ORDER BY n DESC;')
    plan=Optimizer(db,4).plan(q)
    # M3 grouping output aliases must remain resolvable by the physical executor.
    assert sorted(execute(db,plan))==[[1,2],[2,2]]

def test_cross_product(db):
    q=compile_sql(db,'SELECT * FROM Emp e, Dept d;')
    p=Optimizer(db,4).plan(q)
    assert len(execute(db,p))==8

def test_no_stats(db):
    q=compile_sql(db,'SELECT name FROM Emp WHERE age > 30;')
    assert len(execute(db,Optimizer(db,4).plan(q)))==3

def test_order_by_non_projected_column(db):
    q=compile_sql(db,'SELECT name FROM Emp ORDER BY age DESC;')
    p=Optimizer(db,4).plan(q)
    assert execute(db,p)==[['c'],['c'],['a'],['b']]

def test_self_join_aliases(db):
    q=compile_sql(db,'SELECT e.name, m.name FROM Emp e JOIN Emp m ON e.did = m.did;')
    p=Optimizer(db,4).plan(q)
    assert len(execute(db,p))==8

def test_explain_per_node_has_estimates(db):
    q=compile_sql(db,'SELECT name FROM Emp WHERE age > 30;')
    lines=Optimizer(db,4).explain(q).splitlines()
    assert len(lines)>=3 and all('est_rows=' in x and 'est_cost=' in x for x in lines)

def test_union_all_and_distinct(db):
    q=compile_sql(db,'SELECT did FROM Emp UNION ALL SELECT did FROM Dept;')
    p=Optimizer(db,4).plan(q)
    assert len(execute(db,p))==6
    q=compile_sql(db,'SELECT DISTINCT did FROM Emp;')
    assert sorted(execute(db,Optimizer(db,4).plan(q)))==[[1],[2]]

def test_four_way_comma_equals_explicit_join(db):
    for t in ('Emp','Dept','P','T'):analyze(db,t,2)
    a=compile_sql(db,'SELECT e.name FROM Emp e, Dept d, P p, T t WHERE e.did = d.did AND p.did = d.did AND t.did = p.did;')
    b=compile_sql(db,'SELECT e.name FROM Emp e JOIN Dept d ON e.did = d.did JOIN P p ON p.did = d.did JOIN T t ON t.did = p.did;')
    p=Optimizer(db,4).plan(a);q=Optimizer(db,4).plan(b)
    assert sorted(execute(db,p))==sorted(execute(db,q))
