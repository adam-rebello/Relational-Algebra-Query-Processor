class Node:
    """Base class for all AST nodes."""
    pass


class RelationNode(Node):
    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return f"Relation({self.name})"


class SelectNode(Node):
    def __init__(self, condition, child):
        self.condition = condition
        self.child = child

    def __repr__(self):
        return f"Select({self.condition})"


class ProjectNode(Node):
    def __init__(self, attributes, child):
        self.attributes = attributes
        self.child = child

    def __repr__(self):
        return f"Project(attrs={self.attributes})"


class RenameNode(Node):
    def __init__(self, new_name, child):
        self.new_name = new_name
        self.child = child

    def __repr__(self):
        return f"Rename({self.new_name})"


class BinaryNode(Node):
    def __init__(self, left, right):
        self.left = left
        self.right = right


class UnionNode(BinaryNode):
    def __repr__(self):
        return "Union"


class IntersectNode(BinaryNode):
    def __repr__(self):
        return "Intersect"


class MinusNode(BinaryNode):
    def __repr__(self):
        return "Minus"


class TimesNode(BinaryNode):
    def __repr__(self):
        return "Times"


class JoinNode(BinaryNode):
    def __init__(self, condition, left, right):
        super().__init__(left, right)
        self.condition = condition

    def __repr__(self):
        return f"Join({self.condition})"


class ConditionNode(Node):
    pass


class AndNode(BinaryNode, ConditionNode):
    def __repr__(self):
        return "And"


class OrNode(BinaryNode, ConditionNode):
    def __repr__(self):
        return "Or"


class NotNode(ConditionNode):
    def __init__(self, child):
        self.child = child

    def __repr__(self):
        return "Not"


class ComparisonNode(ConditionNode):
    def __init__(self, operator, left, right):
        self.operator = operator
        self.left = left
        self.right = right

    def __repr__(self):
        return f"Compare({self.operator})"


class AttributeNode(Node):
    def __init__(self, name, relation=None):
        self.name = name
        self.relation = relation

    def __repr__(self):
        if self.relation:
            return f"Attr({self.relation}.{self.name})"

        return f"Attr({self.name})"


class NumberNode(Node):
    def __init__(self, value):
        self.value = value

    def __repr__(self):
        return f"Num({self.value})"


class StringNode(Node):
    def __init__(self, value):
        self.value = value

    def __repr__(self):
        return f"String({self.value!r})"