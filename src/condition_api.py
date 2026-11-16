"""Reusable stand-alone condition parsing/evaluation for Modules 2-4."""
from .tokenizer import Tokenizer
from .parser import Parser
from .tokens import TokenType
from .errors import ParseError
from .evaluator import Evaluator
from .relation import RATuple


def parse_condition(text):
    parser = Parser(Tokenizer(text).tokenize())
    node = parser.parse_condition()
    if not parser.check(TokenType.EOF):
        token = parser.current_token()
        raise ParseError(f'Unexpected token {token.value!r}', token.position)
    return node


def evaluate_condition(node, relation, values, other_relation=None, other_values=None):
    """Evaluate condition AST against one tuple or a pair of qualified tuples."""
    evaluator = Evaluator({})
    row = values if isinstance(values, RATuple) else RATuple(values)
    if other_relation is None:
        return evaluator.evaluate_condition(node, relation, row)
    other_row = other_values if isinstance(other_values, RATuple) else RATuple(other_values)
    return evaluator.evaluate_join_condition(node, relation, row, other_relation, other_row)
