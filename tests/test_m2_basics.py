"""Basic real-heap integration tests for the incremental M2 engine."""
import tempfile
import unittest
from pathlib import Path
from storage_engine.core import Catalog, HeapFile
from execution_engine.core import build, PlanError

class ExecutionBasics(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = self.tmp.name
        cat = Catalog(self.db, 4)
        try:
            cat.create_table('R', [['a','INT'], ['b','INT']])
            cat.create_table('S', [['b','INT'], ['c','INT']])
        finally:
            cat.close()
        for name, cols, rows in (
            ('R', [['a','INT'], ['b','INT']], [[1,2],[3,4],[5,2]]),
            ('S', [['b','INT'], ['c','INT']], [[2,20],[2,21],[4,40]]),
        ):
            h = HeapFile(Path(self.db) / (name+'.db'), cols, 4)
            try:
                for row in rows: h.insert(row)
            finally: h.close()

    def run_plan(self, plan):
        op = build(plan, self.db, 4)
        rows = []
        try:
            op.open()
            while True:
                row = op.next()
                if row is None: break
                rows.append(row)
        finally:
            op.close()
        self.assertFalse(op.active)
        return rows

    def test_scan(self):
        self.assertEqual(self.run_plan({'op':'seqscan','table':'R'}), [[1,2],[3,4],[5,2]])

    def test_filter(self):
        self.assertEqual(self.run_plan({'op':'filter', 'condition':'R.a > 2',
                 'child':{'op':'seqscan','table':'R'}}), [[3,4],[5,2]])

    def test_project_keeps_duplicates(self):
        self.assertEqual(self.run_plan({'op':'project','columns':['R.b'],
                 'child':{'op':'seqscan','table':'R'}}), [[2],[4],[2]])

    def test_limit(self):
        self.assertEqual(self.run_plan({'op':'limit','n':1,
                 'child':{'op':'seqscan','table':'R'}}), [[1,2]])

    def test_join_duplicate_keys(self):
        rows = self.run_plan({'op':'nested_loop_join','condition':'R.b = S.b',
             'left':{'op':'seqscan','table':'R'},
             'right':{'op':'seqscan','table':'S'}})
        self.assertEqual(len(rows), 5)
        self.assertEqual(rows.count([1,2,2,20]), 1)
        self.assertEqual(rows.count([5,2,2,21]), 1)

    def test_invalid_plan(self):
        with self.assertRaisesRegex(PlanError, "missing required field 'columns'"):
            build({'op':'project','child':{'op':'seqscan','table':'R'}}, self.db, 4)

    def test_join_requires_condition(self):
        with self.assertRaisesRegex(PlanError, "missing required field"):
            build({'op':'hash_join'}, self.db, 4)

if __name__ == '__main__': unittest.main()
