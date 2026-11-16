"""Safe, deterministic JSON round-tripping for Bonus 1 algebra/condition ASTs."""
import json
from . import ast_nodes

_NODE_TYPES = {name: getattr(ast_nodes, name) for name in (
    'RelationNode', 'SelectNode', 'ProjectNode', 'RenameNode',
    'UnionNode', 'IntersectNode', 'MinusNode', 'TimesNode', 'JoinNode',
    'AndNode', 'OrNode', 'NotNode', 'ComparisonNode', 'AttributeNode',
    'NumberNode', 'StringNode',
)}
_FIELDS = {
    'RelationNode': ('name',),
    'SelectNode': ('condition', 'child'),
    'ProjectNode': ('attributes', 'child'),
    'RenameNode': ('new_name', 'child'),
    'UnionNode': ('left', 'right'),
    'IntersectNode': ('left', 'right'),
    'MinusNode': ('left', 'right'),
    'TimesNode': ('left', 'right'),
    'JoinNode': ('condition', 'left', 'right'),
    'AndNode': ('left', 'right'),
    'OrNode': ('left', 'right'),
    'NotNode': ('child',),
    'ComparisonNode': ('operator', 'left', 'right'),
    'AttributeNode': ('name', 'relation'),
    'NumberNode': ('value',),
    'StringNode': ('value',),
}


def to_dict(node):
    if isinstance(node, list):
        return [to_dict(x) for x in node]
    if node.__class__.__name__ not in _NODE_TYPES or not isinstance(node, ast_nodes.Node):
        return node
    name = type(node).__name__
    return {'node': name, **{field: to_dict(getattr(node, field)) for field in _FIELDS[name]}}


def from_dict(obj):
    if isinstance(obj, list):
        return [from_dict(x) for x in obj]
    if not isinstance(obj, dict):
        return obj
    name = obj.get('node')
    if name not in _NODE_TYPES:
        raise ValueError(f'Unknown AST node: {name!r}')
    fields = _FIELDS[name]
    if set(obj) != set(fields) | {'node'}:
        raise ValueError(f'Unexpected or missing fields for {name}')
    values = [from_dict(obj[field]) for field in fields]
    return _NODE_TYPES[name](*values)


def to_json(node):
    return json.dumps(to_dict(node), ensure_ascii=False, sort_keys=True)


def from_json(text):
    return from_dict(json.loads(text))
