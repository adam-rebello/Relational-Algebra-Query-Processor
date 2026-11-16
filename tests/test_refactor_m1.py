"""Engine refactor: JSON, conditions, bag-mode projection, streaming API."""
import pytest
from src import ast_nodes
from src.condition_api import parse_condition, evaluate_condition
from src.parser import Parser
from src.tokenizer import Tokenizer
from src.relation import Relation
from src.evaluator import Evaluator
from src.tree_json import to_json, from_json


def test_every_tree_node_round_trip():
    a = ast_nodes.AttributeNode('b','R')
    b = ast_nodes.AttributeNode('b','S')
    cond = ast_nodes.ComparisonNode('=', a, b)
    nodes = [
        ast_nodes.RelationNode('R'), ast_nodes.SelectNode(cond, ast_nodes.RelationNode('R')),
        ast_nodes.ProjectNode([a],ast_nodes.RelationNode('R')),
        ast_nodes.RenameNode('U',ast_nodes.RelationNode('R')),
        ast_nodes.UnionNode(ast_nodes.RelationNode('R'),ast_nodes.RelationNode('S')),
        ast_nodes.IntersectNode(ast_nodes.RelationNode('R'),ast_nodes.RelationNode('S')),
        ast_nodes.MinusNode(ast_nodes.RelationNode('R'),ast_nodes.RelationNode('S')),
        ast_nodes.TimesNode(ast_nodes.RelationNode('R'),ast_nodes.RelationNode('S')),
        ast_nodes.JoinNode(cond,ast_nodes.RelationNode('R'),ast_nodes.RelationNode('S')),
        ast_nodes.AndNode(cond,cond), ast_nodes.OrNode(cond,cond),
        ast_nodes.NotNode(cond), cond, a, ast_nodes.NumberNode(-10),
        ast_nodes.StringNode('test'),
    ]
    for node in nodes:
        assert to_json(from_json(to_json(node))) == to_json(node)


def test_condition_independent_parser():
    r=Relation('R',['a','b']);s=Relation('S',['b'])
    cond=parse_condition('R.b = S.b and R.a > 4')
    assert evaluate_condition(cond,r,[5,2],s,[2]) is True
    assert evaluate_condition(cond,r,[3,2],s,[2]) is False
    single=parse_condition('R.a > 4')
    assert evaluate_condition(single,r,[5,2]) is True
    with pytest.raises(Exception):
        parse_condition('R.a = 4 nonsense')


def test_projection_keeps_bag_duplicates_but_legacy_unchanged():
    r=Relation('R',['id','name'],bag=True)
    r.add_tuple([1,'bob']);r.add_tuple([2,'bob']);r.add_tuple([2,'bob'])
    query=Parser(Tokenizer('project[name](R)').tokenize()).parse()
    result=Evaluator({'R':r}).evaluate(query)
    assert [x.values for x in result.tuples] == [['bob'],['bob'],['bob']]
    assert [x.values for x in result.distinct().tuples] == [['bob']]
    assert list(r.iter_rows()) == r.tuples
    legacy=Relation('R',['name']);legacy.add_tuple(['bob']);legacy.add_tuple(['bob'])
    assert len(legacy.tuples)==1
