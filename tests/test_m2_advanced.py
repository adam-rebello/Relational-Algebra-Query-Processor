import unittest
from tests.test_m2_basics import ExecutionBasics
from execution_engine.core import build

class AdvancedOps(ExecutionBasics):
    def test_sorts(self):
        x=self.run_plan({'op':'sort','keys':[['R.b','asc'],['R.a','desc']], 'child':{'op':'seqscan','table':'R'}})
        self.assertEqual(x,[[5,2],[1,2],[3,4]])
    def test_distinct(self):
        x=self.run_plan({'op':'distinct','mode':'sort','child':{'op':'project','columns':['R.b'],'child':{'op':'seqscan','table':'R'}}})
        self.assertEqual(x,[[2],[4]])
    def test_group(self):
        x=self.run_plan({'op':'group_by','mode':'sort','keys':['R.b'],'aggregates':[['count','*'],['sum','R.a']], 'child':{'op':'seqscan','table':'R'}})
        self.assertEqual(x,[[2,2,6],[4,1,3]])
    def test_all_joins(self):
        base={'condition':'R.b = S.b','left':{'op':'seqscan','table':'R'},'right':{'op':'seqscan','table':'S'}}
        expected=sorted(self.run_plan({'op':'nested_loop_join',**base}))
        for op in ('sort_merge_join','hash_join'):
            self.assertEqual(sorted(self.run_plan({'op':op,**base})),expected)
    def test_set_ops(self):
        r={'op':'project','columns':['R.b'],'child':{'op':'seqscan','table':'R'}}
        s={'op':'project','columns':['S.b'],'child':{'op':'seqscan','table':'S'}}
        for op,expected in [('union',[[2],[4]]),('intersect',[[2],[4]]),('except',[])]:
            self.assertEqual(self.run_plan({'op':op,'left':r,'right':s}),expected)
