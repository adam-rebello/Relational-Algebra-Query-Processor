"""Module 3 contract cases taken from the instructor's required-case list."""
import pytest
from sql_frontend.compiler import Parser,Compiler,SQLError

@pytest.fixture
def compiler():
    return Compiler({k:{'schema':v} for k,v in {
        'Emp':[['eid','INT'],['name','VARCHAR',20],['age','INT'],['mgr','INT'],['did','INT'],['salary','INT'],['city','VARCHAR',20]],
        'Dept':[['did','INT'],['title','VARCHAR',20],['budget','INT'],['city','VARCHAR',20]],
        'P':[['pid','INT'],['did','INT']], 'T':[['tid','INT'],['did','INT']]}.items()})

def compile_(c,q):return c.compile(Parser(q).parse())
def expect_err(c,q,cat):
    with pytest.raises(SQLError) as e:compile_(c,q)
    assert e.value.category==cat

def walk(n):
    if isinstance(n,dict):
        yield n
        for v in n.values():yield from walk(v)
    elif isinstance(n,list):
        for v in n:yield from walk(v)

def test_01_self_join(compiler):
    p=compile_(compiler,'SELECT e.name, m.name FROM Emp e JOIN Emp m ON e.mgr = m.eid;')
    assert [n['to'] for n in walk(p) if n.get('op')=='rename']==['e','m']

def test_02_star_three_tables(compiler):
    p=compile_(compiler,'SELECT * FROM Emp e, Dept d, P p;')
    assert 'e.did' in p['columns'] and 'd.did' in p['columns'] and 'p.did' in p['columns']

def test_03_ambiguous_column(compiler):expect_err(compiler,'SELECT did FROM Emp, Dept;','ambiguity')
def test_04_union_modes(compiler):
    a=compile_(compiler,'SELECT city FROM Emp UNION SELECT city FROM Dept;')
    b=compile_(compiler,'SELECT city FROM Emp UNION ALL SELECT city FROM Dept;')
    assert (a['op'],b['op'])==('union','union_all')

def test_05_where_having(compiler):
    p=compile_(compiler,'SELECT did,COUNT(*) AS n FROM Emp WHERE age > 25 GROUP BY did HAVING COUNT(*) > 5;')
    sels=[n['condition'] for n in walk(p) if n.get('op')=='select']
    assert 'n > 5' in sels and 'Emp.age > 25' in sels

def test_06_non_grouped(compiler):expect_err(compiler,'SELECT name,COUNT(*) FROM Emp GROUP BY did;','aggregate')
def test_07_aggregate_where(compiler):expect_err(compiler,'SELECT name FROM Emp WHERE COUNT(*) > 3;','aggregate')

def test_08_subquery_join(compiler):
    p=compile_(compiler,'SELECT t.did,d.title FROM (SELECT did,COUNT(*) AS n FROM Emp GROUP BY did) AS t JOIN Dept d ON t.did = d.did;')
    assert any(n.get('op')=='rename' and n.get('to')=='t' for n in walk(p))

def test_09_order_nonproject(compiler):
    p=compile_(compiler,'SELECT name FROM Emp ORDER BY age DESC;')
    assert p['keys']==[['Emp.age','desc']]

def test_10_bad_comparison(compiler):expect_err(compiler,"SELECT name FROM Emp WHERE age > '30';",'type')

def test_11_unknown_names(compiler):
    expect_err(compiler,'SELECT x FROM Missing;','name')
    expect_err(compiler,'SELECT absent FROM Emp;','name')

def test_12_duplicate_alias(compiler):expect_err(compiler,'SELECT * FROM Emp, Emp;','name')

def test_13_no_group_count(compiler):
    p=compile_(compiler,'SELECT COUNT(*) FROM Emp;')
    assert any(n.get('op')=='group_by' and n['keys']==[] for n in walk(p))

def test_14_set_mismatch(compiler):expect_err(compiler,'SELECT age FROM Emp UNION SELECT city FROM Dept;','schema')

def test_15_four_table_forms(compiler):
    a=compile_(compiler,'SELECT * FROM Emp e, Dept d, P p, T t WHERE e.did = d.did AND p.did = d.did AND t.did = p.did;')
    b=compile_(compiler,'SELECT * FROM Emp e JOIN Dept d ON e.did = d.did JOIN P p ON p.did = d.did JOIN T t ON t.did = p.did;')
    assert len([x for x in walk(a) if x.get('op')=='cross'])==3
    assert len([x for x in walk(b) if x.get('op')=='join'])==3
