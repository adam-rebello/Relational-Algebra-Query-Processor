"""Small hidden-test-style cases for the execution engine."""
import pathlib
import tempfile
import unittest
from storage_engine.core import Catalog,HeapFile
from execution_engine.core import build,PlanError,nodes

class Edges(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db=self.tmp.name
        c=Catalog(self.db,4)
        c.create_table('A',[['k','INT'],['x','INT']])
        c.create_table('B',[['k','INT'],['y','INT']])
        c.create_table('Empty',[['k','INT'],['x','INT']])
        c.close()
        for table,schema,rows in [('A',[['k','INT'],['x','INT']],[[1,7],[2,7],[2,7],[3,9]]),
                                  ('B',[['k','INT'],['y','INT']],[[2,8],[2,8],[4,8]])]:
            h=HeapFile(pathlib.Path(self.db)/(table+'.db'),schema,4)
            for row in rows:h.insert(row)
            h.close()
    def run_plan(self,plan,B=4):
        op=build(plan,self.db,B)
        rows=[]
        try:
            op.open()
            while True:
                row=op.next()
                if row is None:break
                rows.append(row)
        finally:op.close()
        return rows,op
    def test_join_duplicate_cartesian_product(self):
        for algorithm in ('nested_loop_join','sort_merge_join','hash_join'):
            rows,op=self.run_plan({'op':algorithm,'condition':'A.k = B.k',
                            'left':{'op':'seqscan','table':'A'},'right':{'op':'seqscan','table':'B'}})
            self.assertEqual(len(rows),4,algorithm)
            self.assertEqual(rows.count([2,7,2,8]),4)
            if algorithm=='nested_loop_join': self.assertEqual(op.comparisons,12)
    def test_hash_distinct_and_hash_group(self):
        for mode in ('sort','hash'):
            rows,_=self.run_plan({'op':'distinct','mode':mode,'child':{'op':'project','columns':['A.x'],'child':{'op':'seqscan','table':'A'}}})
            self.assertEqual(sorted(rows),[[7],[9]])
            rows,_=self.run_plan({'op':'group_by','mode':mode,'keys':['A.x'],'aggregates':[['count','*'],['sum','A.k'],['avg','A.k']], 'child':{'op':'seqscan','table':'A'}})
            self.assertEqual(sorted(rows),[[7,3,5,1.6667],[9,1,3,3.0]])
    def test_empty_group(self):
        rows,_=self.run_plan({'op':'group_by','mode':'hash','keys':[],'aggregates':[['count','*']],'child':{'op':'seqscan','table':'Empty'}})
        self.assertEqual(rows,[[0]])
        rows,_=self.run_plan({'op':'group_by','mode':'sort','keys':['Empty.k'],'aggregates':[['count','*']],'child':{'op':'seqscan','table':'Empty'}})
        self.assertEqual(rows,[])
    def test_set_ops(self):
        a={'op':'project','columns':['A.x'],'child':{'op':'seqscan','table':'A'}}
        b={'op':'project','columns':['B.y'],'child':{'op':'seqscan','table':'B'}}
        self.assertEqual(self.run_plan({'op':'union','left':a,'right':b})[0],[[7],[8],[9]])
        self.assertEqual(self.run_plan({'op':'intersect','left':a,'right':b})[0],[])
        self.assertEqual(self.run_plan({'op':'except','left':a,'right':b})[0],[[7],[9]])
    def test_invalid_column_and_type(self):
        for condition in ('A.missing = 1', "A.x = 'bad'",'A.x = B.y'):
            with self.assertRaises(PlanError):
                build({'op':'filter','condition':condition,'child':{'op':'seqscan','table':'A'}},self.db,4)
    def test_unknown_table(self):
        with self.assertRaises(Exception): build({'op':'seqscan','table':'Nope'},self.db,4)
    def test_limit_zero_stops(self):
        self.assertEqual(self.run_plan({'op':'limit','n':0,'child':{'op':'seqscan','table':'A'}})[0],[])
    def test_hash_join_skew_fallback(self):
        for tab in ('A','B'):
            h=HeapFile(pathlib.Path(self.db)/(tab+'.db'),[['k','INT'],['x' if tab=='A' else 'y','INT']],4)
            for i in range(1100):h.insert([1,i])
            h.close()
        # Limit output to avoid materializing >1 million rows, but let the join open partition.
        plan={'op':'limit','n':5,'child':{'op':'hash_join','condition':'A.k = B.k',
             'left':{'op':'seqscan','table':'A'},'right':{'op':'seqscan','table':'B'}}}
        rows,root=self.run_plan(plan)
        self.assertEqual(len(rows),5)
        self.assertGreaterEqual(root.child.overflow_partitions,1)
