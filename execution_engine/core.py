"""Iterator execution against the Module 1 heap-file API.

Supported: seqscan, filter, project, limit, union_all, nested_loop_join.
Other Module 2 operations deliberately fail validation rather than silently
substitute an algorithm with incorrect memory/I/O behavior.
"""
from pathlib import Path
from storage_engine.core import Catalog, HeapFile
from src.condition_api import parse_condition, evaluate_condition
from src.relation import Relation, Attribute

class PlanError(Exception):
    pass

class Operator:
    def __init__(self, name):
        self.name = name
        self.schema = []
        self.children = []
        self.tuples_out = 0
        self.comparisons = 0
        self.page_reads = 0
        self.page_writes = 0
        self.active = False

    def open(self):
        self.active = True

    def next(self):
        raise NotImplementedError()

    def close(self):
        self.active = False

    def counters(self):
        return dict(tuples_out=self.tuples_out, comparisons=self.comparisons,
                    page_reads=self.page_reads, page_writes=self.page_writes)

    def emit(self, row):
        if row is not None:
            self.tuples_out += 1
        return row

class SeqScan(Operator):
    def __init__(self, db, table, frames):
        super().__init__(f'seqscan {table}')
        self.db, self.table, self.frames = db, table, frames
        cat = Catalog(db, frames)
        try:
            info = cat.get_table(table)
        finally:
            cat.close()
        self.raw_schema = info['schema']
        self.filename = info['file']
        self.schema = [[table + '.' + c[0], *c[1:]] for c in self.raw_schema]
        self.heap = None
        self.iterator = None

    def open(self):
        super().open()
        self.heap = HeapFile(Path(self.db) / self.filename, self.raw_schema, min(self.frames, 2))
        self.iterator = self.heap.scan()

    def next(self):
        try:
            _, row = next(self.iterator)
            return self.emit(row)
        except StopIteration:
            return None

    def close(self):
        if self.iterator is not None:
            self.iterator.close()
            self.iterator = None
        if self.heap is not None:
            stats = self.heap.pool.stats()
            self.page_reads += stats['reads']
            self.page_writes += stats['writes']
            self.heap.close()
            self.heap = None
        super().close()

class Unary(Operator):
    def __init__(self, name, child):
        super().__init__(name)
        self.child = child
        self.children = [child]
        self.schema = child.schema

    def open(self):
        self.child.open()
        super().open()

    def close(self):
        try:
            self.child.close()
        finally:
            super().close()

class Filter(Unary):
    def __init__(self, child, condition):
        super().__init__('filter', child)
        self.condition = parse_condition(condition)
        self.relation = relation_for_schema(child.schema)
        check_condition(self.condition, child.schema)

    def next(self):
        while True:
            row = self.child.next()
            if row is None:
                return None
            self.comparisons += 1
            if evaluate_condition(self.condition, self.relation, row):
                return self.emit(row)

class Project(Unary):
    def __init__(self, child, columns):
        super().__init__('project', child)
        self.indexes = [column_index(child.schema, col) for col in columns]
        self.schema = [child.schema[i] for i in self.indexes]

    def next(self):
        row = self.child.next()
        return None if row is None else self.emit([row[i] for i in self.indexes])

class Rename(Unary):
    """Pipelined relation alias, preserving tuple values and positions."""
    def __init__(self, child, alias):
        super().__init__('rename', child)
        self.schema = [[alias + '.' + c[0].split('.')[-1], *c[1:]] for c in child.schema]

    def next(self):
        return self.emit(self.child.next())

class Limit(Unary):
    def __init__(self, child, n):
        super().__init__('limit', child)
        self.n = n

    def next(self):
        if self.tuples_out >= self.n:
            return None
        return self.emit(self.child.next())

class UnionAll(Operator):
    def __init__(self, left, right):
        super().__init__('union_all')
        if [x[1:] for x in left.schema] != [x[1:] for x in right.schema]:
            raise PlanError("Node 'union_all': incompatible schemas")
        self.left, self.right = left, right
        self.schema = left.schema
        self.children = [left, right]
        self.using_left = True

    def open(self):
        self.left.open()
        self.using_left = True
        super().open()

    def next(self):
        if self.using_left:
            row = self.left.next()
            if row is not None:
                return self.emit(row)
            self.left.close()
            self.using_left = False
            self.right.open()
        return self.emit(self.right.next())

    def close(self):
        if self.using_left:
            self.left.close()
        else:
            self.right.close()
        super().close()

class NestedLoopJoin(Operator):
    """Correct tuple-streaming nested loop baseline, NOT the required block algorithm.

    The B-2 outer-page buffering and textbook I/O cost are NOT implemented.
    """
    def __init__(self, left, right, condition):
        super().__init__('nested_loop_join')
        self.left, self.right = left, right
        self.children = [left, right]
        self.schema = left.schema + right.schema
        if len({x[0] for x in self.schema}) != len(self.schema):
            raise PlanError("Node 'nested_loop_join': duplicate qualified column")
        self.condition = parse_condition(condition)
        self.relation = relation_for_schema(self.schema)
        self.current_left = None
        self.right_active = False

    def open(self):
        self.left.open()
        self.current_left = None
        self.right_active = False
        super().open()

    def next(self):
        while True:
            if self.current_left is None:
                self.current_left = self.left.next()
                if self.current_left is None:
                    return None
                self.right.open()
                self.right_active = True
            right_row = self.right.next()
            if right_row is None:
                self.right.close()
                self.right_active = False
                self.current_left = None
                continue
            candidate = self.current_left + right_row
            self.comparisons += 1
            if evaluate_condition(self.condition, self.relation, candidate):
                return self.emit(candidate)

    def close(self):
        if self.right_active:
            self.right.close()
            self.right_active = False
        self.left.close()
        super().close()


def check_condition(node, schema):
    """Resolve every qualified attribute and reject type mismatches before I/O."""
    from src.ast_nodes import (AndNode, OrNode, NotNode, ComparisonNode,
                               AttributeNode, NumberNode, StringNode)
    def operand_type(part):
        if isinstance(part, NumberNode): return 'INT'
        if isinstance(part, StringNode): return 'VARCHAR'
        if isinstance(part, AttributeNode):
            if not part.relation:
                index=column_index(schema,part.name)
            else:
                index=column_index(schema,part.relation+'.'+part.name)
            return schema[index][1]
        raise PlanError('Invalid condition operand')
    def check(part):
        if isinstance(part, (AndNode,OrNode)):
            check(part.left);check(part.right)
        elif isinstance(part, NotNode):check(part.child)
        elif isinstance(part, ComparisonNode):
            a,b=operand_type(part.left),operand_type(part.right)
            if a!=b:raise PlanError(f'Condition type mismatch: {a} and {b}')
        else:raise PlanError('Invalid condition expression')
    check(node)


def relation_for_schema(schema):
    attrs = []
    for name, *rest in schema:
        if '.' in name:
            table, col = name.split('.', 1)
        else:
            table, col = None, name
        attrs.append(Attribute(col, relation=table,
                               value_type='number' if rest[0] == 'INT' else 'string'))
    return Relation('_condition', attrs, bag=True)


def column_index(schema, name):
    matching = [i for i, c in enumerate(schema) if c[0] == name]
    if len(matching) != 1:
        raise PlanError(f'Unknown or ambiguous column {name!r}')
    return matching[0]


def validate(node, path='root'):
    if not isinstance(node, dict):
        raise PlanError(f"Node '{path}': must be an object")
    op = node.get('op')
    if not isinstance(op, str):
        raise PlanError(f"Node '{path}': missing required string field 'op'")
    fields = {
        'seqscan': {'table': str},
        'rename': {'to': str, 'child': dict},
        'filter': {'condition': str, 'child': dict},
        'project': {'columns': list, 'child': dict},
        'limit': {'n': int, 'child': dict},
        'sort': {'keys': list, 'child': dict},
        'distinct': {'mode': str, 'child': dict},
        'group_by': {'mode': str, 'keys': list, 'aggregates': list, 'child': dict},
        'union_all': {'left': dict, 'right': dict},
        'union': {'left': dict, 'right': dict},
        'intersect': {'left': dict, 'right': dict},
        'except': {'left': dict, 'right': dict},
        'nested_loop_join': {'condition': str, 'left': dict, 'right': dict},
        'sort_merge_join': {'condition': str, 'left': dict, 'right': dict},
        'hash_join': {'condition': str, 'left': dict, 'right': dict},
    }
    if op not in fields:
        raise PlanError(f"Node '{path}': unsupported operator '{op}' in current M2 build")
    for key, typ in fields[op].items():
        if key not in node:
            raise PlanError(f"Node '{op}': missing required field '{key}'")
        if not isinstance(node[key], typ):
            raise PlanError(f"Node '{op}': field '{key}' must be {typ.__name__}")
    if op in ('distinct','group_by') and node['mode'] not in ('sort','hash'):
        raise PlanError(f"Node '{op}': mode must be sort or hash")
    if op == 'sort' and any(not isinstance(k, list) or len(k)!=2 or not all(isinstance(x,str) for x in k) or k[1].lower() not in ('asc','desc') for k in node['keys']):
        raise PlanError("Node 'sort': keys must be [column,direction] pairs")
    if op == 'group_by' and (not all(isinstance(x,str) for x in node['keys']) or any(not isinstance(a,list) or len(a) not in (2,3) or not all(isinstance(x,str) for x in a) for a in node['aggregates'])):
        raise PlanError("Node 'group_by': invalid keys or aggregates")
    if op == 'project' and (not node['columns'] or not all(isinstance(c, str) for c in node['columns'])):
        raise PlanError("Node 'project': columns must be a nonempty string list")
    if op == 'limit' and (type(node['n']) is not int or node['n'] < 0):
        raise PlanError("Node 'limit': n must be a nonnegative integer")
    for child_key in ('child', 'left', 'right'):
        if child_key in node:
            validate(node[child_key], op + '.' + child_key)


def build(node, db, frames):
    validate(node)
    op = node['op']
    if op == 'seqscan':
        return SeqScan(db, node['table'], frames)
    if op in ('rename', 'filter', 'project', 'limit', 'sort', 'distinct', 'group_by'):
        child = build(node['child'], db, frames)
        if op == 'rename': return Rename(child, node['to'])
        if op == 'filter': return Filter(child, node['condition'])
        if op == 'project': return Project(child, node['columns'])
        if op == 'limit': return Limit(child, node['n'])
        from .advanced import ExternalSort, Distinct, GroupBy, HashDistinct, HashGroupBy
        if op == 'sort': return ExternalSort(child, node['keys'], frames)
        if op == 'distinct': return HashDistinct(child,frames) if node['mode']=='hash' else Distinct(child,'sort',frames)
        return HashGroupBy(child,node['keys'],node['aggregates'],frames) if node['mode']=='hash' else GroupBy(child,node['keys'],node['aggregates'],'sort',frames)
    left = build(node['left'], db, frames)
    right = build(node['right'], db, frames)
    if op == 'union_all': return UnionAll(left, right)
    from .advanced import SetOperation, BlockNestedLoop, SortMergeJoin, GraceHashJoin
    if op in ('union','intersect','except'): return SetOperation(op,left,right,frames)
    if op == 'nested_loop_join': return BlockNestedLoop(left,right,node['condition'],frames)
    if op == 'sort_merge_join': return SortMergeJoin(left,right,node['condition'],frames)
    return GraceHashJoin(left,right,node['condition'],frames)

def nodes(root, depth=0):
    yield depth, root
    for child in root.children:
        yield from nodes(child, depth + 1)
