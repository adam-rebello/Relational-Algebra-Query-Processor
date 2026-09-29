import pytest

from src.tokenizer import Tokenizer
from src.parser import Parser
from src.errors import ParseError

from src.ast_nodes import (
    UnionNode,
    MinusNode,
    IntersectNode,
    ProjectNode,
    SelectNode,
    OrNode,
    AndNode,
    NotNode
)


def parse_query(text):
    tokens = Tokenizer(text).tokenize()
    return Parser(tokens).parse()


def test_union_minus_grouping():
    # Case 10: A union B minus C
    tree = parse_query("A union B minus C")

    assert isinstance(tree, MinusNode)
    assert isinstance(tree.left, UnionNode)


def test_minus_left_associative():
    # Case 11: A minus B minus C
    tree = parse_query("A minus B minus C")

    assert isinstance(tree, MinusNode)
    assert isinstance(tree.left, MinusNode)


def test_condition_precedence_with_not():
    # Case 12
    tree = parse_query(
        "select[not (a=1 and b=2) or c>3](R)"
    )

    assert isinstance(tree, SelectNode)
    assert isinstance(tree.condition, OrNode)
    assert isinstance(tree.condition.left, NotNode)


def test_and_before_or():
    # Case 13
    tree = parse_query(
        "select[a=1 and b=2 or c=3](R)"
    )

    assert isinstance(tree, SelectNode)
    assert isinstance(tree.condition, OrNode)
    assert isinstance(tree.condition.left, AndNode)


def test_nested_unary_expressions():
    # Case 14
    tree = parse_query(
        "project[Name]("
        "select[Age>30]("
        "select[DID='D1'](Employees)"
        ")"
        ")"
    )

    assert isinstance(tree, ProjectNode)
    assert isinstance(tree.child, SelectNode)
    assert isinstance(tree.child.child, SelectNode)


def test_parentheses_override_precedence():
    # Case 15
    tree = parse_query(
        "(A union B) minus (C intersect D)"
    )

    assert isinstance(tree, MinusNode)
    assert isinstance(tree.left, UnionNode)
    assert isinstance(tree.right, IntersectNode)


def test_missing_parenthesis():
    # Case 16
    with pytest.raises(ParseError) as error:
        parse_query("select[Age>30](R")

    assert "Expected ')'" in str(error.value)
    assert error.value.position >= 0


def test_empty_projection_list():
    # Case 17
    with pytest.raises(ParseError) as error:
        parse_query("project[](R)")

    assert "cannot be empty" in str(error.value)