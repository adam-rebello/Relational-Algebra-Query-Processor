"""Additional contract-oriented checks for the Module 2 submission audit."""
import pathlib
import tempfile
import unittest
from collections import Counter
from storage_engine.core import Catalog, HeapFile
from execution_engine.core import build, PlanError


class SubmissionAudit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = self.tmp.name
        self.data = {
            'A': [[1, 4], [2, 5], [2, 5], [3, -3]],
            'B': [[2, 9], [2, 9], [4, 1]],
            'E': [],
        }
        cat = Catalog(self.db, 4)
        for table, rows in self.data.items():
            cat.create_table(table, [['k','INT'],['v','INT']])
        cat.close()
        for table, rows in self.data.items():
            h = HeapFile(pathlib.Path(self.db) / (table+'.db'), [['k','INT'],['v','INT']], 4)
            for row in rows: h.insert(row)
            h.close()

    def execute(self, plan, B=4):
        root = build(plan, self.db, B)
        rows = []
        try:
            root.open()
            while True:
                row = root.next()
                if row is None: break
                rows.append(row)
        finally:
            root.close()
        return rows, root

    def scan(self, table): return {'op':'seqscan', 'table':table}

    def test_join_bag_and_comparisons_multiple_budgets(self):
        base = {'condition':'A.k = B.k', 'left':self.scan('A'), 'right':self.scan('B')}
        expected=Counter({(2,5,2,9): 4})
        for B in (4, 5, 16):
            for alg in ('nested_loop_join','sort_merge_join','hash_join'):
                rows,root = self.execute({'op':alg, **base}, B)
                self.assertEqual(Counter(tuple(r) for r in rows),expected,(B,alg))
                if alg=='nested_loop_join':self.assertEqual(root.comparisons,12)

    def test_nested_aggregate_and_sort(self):
        group={'op':'group_by','mode':'sort','keys':['A.k'],
               'aggregates':[['avg','A.v'], ['count','*']], 'child':self.scan('A')}
        sort={'op':'sort','keys':[['A.k','asc']],'child':group}
        rows,_=self.execute(sort)
        self.assertEqual(rows,[[1,4.0,1],[2,5.0,2],[3,-3.0,1]])

    def test_limit_on_sort_and_join(self):
        join={'op':'hash_join','condition':'A.k = B.k','left':self.scan('A'),'right':self.scan('B')}
        rows,_=self.execute({'op':'limit','n':1,'child':join})
        self.assertEqual(len(rows),1)
        sort={'op':'sort','keys':[['A.v','desc']],'child':self.scan('A')}
        rows,_=self.execute({'op':'limit','n':2,'child':sort})
        self.assertEqual(rows,[[2,5],[2,5]])

    def test_empty_ops(self):
        for op in ('sort','distinct','group_by'):
            plan={'op':op,'child':self.scan('E')}
            if op=='sort':plan['keys']=[['E.k','asc']]
            if op=='distinct':plan['mode']='hash'
            if op=='group_by':plan.update(mode='hash',keys=['E.k'],aggregates=[['count','*']])
            rows,_=self.execute(plan)
            self.assertEqual(rows,[])
        for op in ('nested_loop_join','sort_merge_join','hash_join'):
            rows,_=self.execute({'op':op,'condition':'E.k = B.k','left':self.scan('E'),'right':self.scan('B')})
            self.assertEqual(rows,[])

    def test_invalid_plans(self):
        cases=[{'op':'sort','child':self.scan('A')},
               {'op':'filter','condition':3,'child':self.scan('A')},
               {'op':'sort','keys':[['A.k','sideways']],'child':self.scan('A')},
               {'op':'project','columns':['A.z'],'child':self.scan('A')}]
        for case in cases:
            with self.assertRaises(PlanError):build(case,self.db,4)

    def test_set_operations_with_duplicates(self):
        a={'op':'project','columns':['A.k'],'child':self.scan('A')}
        b={'op':'project','columns':['B.k'],'child':self.scan('B')}
        expected={'union':[[1],[2],[3],[4]],'intersect':[[2]],'except':[[1],[3]],
                  'union_all':[[1],[2],[2],[3],[2],[2],[4]]}
        for op,exp in expected.items():
            rows,_=self.execute({'op':op,'left':a,'right':b})
            self.assertEqual(Counter(tuple(r) for r in rows),Counter(tuple(r) for r in exp))

if __name__=='__main__':unittest.main()

class ExtraVerifier(SubmissionAudit):
    def test_intermediate_real_distinct_and_sort(self):
        group={'op':'group_by','mode':'hash','keys':['A.k'],
               'aggregates':[['avg','A.v']],'child':self.scan('A')}
        distinct={'op':'distinct','mode':'hash','child':group}
        rows,_=self.execute({'op':'sort','keys':[['avg_A_v','desc']],'child':distinct})
        self.assertEqual(rows,[[2,5.0],[1,4.0],[3,-3.0]])

    def test_consecutive_runs_have_equal_counters(self):
        plan={'op':'sort','keys':[['A.k','desc']],'child':self.scan('A')}
        first,root1=self.execute(plan)
        second,root2=self.execute(plan)
        self.assertEqual(first,second)
        self.assertEqual(root1.counters(),root2.counters())

    def test_temporary_files_removed_after_short_circuit(self):
        import glob, tempfile
        before=set(glob.glob(str(pathlib.Path(tempfile.gettempdir())/'m2_*.db')))
        plan={'op':'limit','n':1, 'child':{'op':'sort','keys':[['A.v','desc']],'child':self.scan('A')}}
        self.execute(plan)
        after=set(glob.glob(str(pathlib.Path(tempfile.gettempdir())/'m2_*.db')))
        self.assertEqual(after-before,set())

    def test_empty_global_aggregate_semantics(self):
        for mode in ('hash','sort'):
            plan={'op':'group_by','mode':mode,'keys':[], 'aggregates':[['count','*']], 'child':self.scan('E')}
            self.assertEqual(self.execute(plan)[0],[[0]])
            plan['aggregates']=[['avg','E.v']]
            with self.assertRaises(PlanError):self.execute(plan)
