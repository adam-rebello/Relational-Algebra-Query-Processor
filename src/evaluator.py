from .relation import Relation, Attribute
from .errors import SchemaError, TypeErrorRA, NameErrorRA

from .ast_nodes import (
    RelationNode,
    SelectNode,
    ProjectNode,
    RenameNode,
    UnionNode,
    IntersectNode,
    MinusNode,
    TimesNode,
    JoinNode,
    AndNode,
    OrNode,
    NotNode,
    ComparisonNode,
    AttributeNode,
    NumberNode,
    StringNode
)


class Evaluator:
    def __init__(self, relations):
        """
        relations is a dictionary such as:

        {
            "Employees": employees_relation,
            "Dept": dept_relation
        }
        """
        self.relations = relations

        self.join_comparisons = 0
        self.select_comparisons = 0

    def evaluate(self, node):

        if isinstance(node, RelationNode):
            return self.evaluate_relation(node)

        if isinstance(node, SelectNode):
            return self.evaluate_select(node)

        if isinstance(node, ProjectNode):
            return self.evaluate_project(node)

        if isinstance(node, RenameNode):
            return self.evaluate_rename(node)

        if isinstance(node, UnionNode):
            return self.evaluate_union(node)

        if isinstance(node, IntersectNode):
            return self.evaluate_intersect(node)

        if isinstance(node, MinusNode):
            return self.evaluate_minus(node)

        if isinstance(node, TimesNode):
            return self.evaluate_times(node)

        if isinstance(node, JoinNode):
            return self.evaluate_join(node)

        raise TypeErrorRA(
            f"Unknown AST node: {type(node).__name__}"
        )

    # ---------------------------------------------------------
    # Relation
    # ---------------------------------------------------------

    def evaluate_relation(self, node):
        if node.name not in self.relations:
            raise NameErrorRA(
                f"Unknown relation {node.name}"
            )

        return self.relations[node.name]

    # ---------------------------------------------------------
    # Select
    # ---------------------------------------------------------

    def evaluate_select(self, node):
        relation = self.evaluate(node.child)

        result = relation.copy_schema()

        for row in relation.tuples:
            self.select_comparisons += 1

            if self.evaluate_condition(
                node.condition,
                relation,
                row
            ):
                result.add_tuple(row.values)

        return result

    # ---------------------------------------------------------
    # Project
    # ---------------------------------------------------------

    def evaluate_project(self, node):
        relation = self.evaluate(node.child)

        indexes = []
        attributes = []
        seen = set()

        for attr_node in node.attributes:

            key = (
                attr_node.relation,
                attr_node.name
            )

            if key in seen:
                raise SchemaError(
                    f"Duplicate projection attribute "
                    f"{attr_node.name}"
                )

            seen.add(key)

            index = relation.get_attribute_index(
                attr_node.name,
                attr_node.relation
            )

            indexes.append(index)

            old_attr = relation.attributes[index]

            attributes.append(
                Attribute(
                    old_attr.name,
                    old_attr.relation,
                    old_attr.value_type
                )
            )

        result = Relation(
            relation.name,
            attributes
        )

        for row in relation.tuples:
            values = [
                row.values[i]
                for i in indexes
            ]

            result.add_tuple(values)

        return result

    # ---------------------------------------------------------
    # Rename
    # ---------------------------------------------------------

    def evaluate_rename(self, node):
        relation = self.evaluate(node.child)

        attributes = []

        for attribute in relation.attributes:
            attributes.append(
                Attribute(
                    attribute.name,
                    node.new_name,
                    attribute.value_type
                )
            )

        result = Relation(
            node.new_name,
            attributes
        )

        for row in relation.tuples:
            result.add_tuple(row.values)

        return result

    # ---------------------------------------------------------
    # Set operators
    # ---------------------------------------------------------

    def evaluate_union(self, node):
        left = self.evaluate(node.left)
        right = self.evaluate(node.right)

        self.check_union_compatible(left, right)

        result = left.copy_schema()

        for row in left.tuples:
            result.add_tuple(row.values)

        for row in right.tuples:
            result.add_tuple(row.values)

        return result

    def evaluate_intersect(self, node):
        left = self.evaluate(node.left)
        right = self.evaluate(node.right)

        self.check_union_compatible(left, right)

        result = left.copy_schema()

        for left_row in left.tuples:
            for right_row in right.tuples:
                if left_row == right_row:
                    result.add_tuple(left_row.values)
                    break

        return result

    def evaluate_minus(self, node):
        left = self.evaluate(node.left)
        right = self.evaluate(node.right)

        self.check_union_compatible(left, right)

        result = left.copy_schema()

        for left_row in left.tuples:
            found = False

            for right_row in right.tuples:
                if left_row == right_row:
                    found = True
                    break

            if not found:
                result.add_tuple(left_row.values)

        return result

    # ---------------------------------------------------------
    # Cartesian product
    # ---------------------------------------------------------

    def evaluate_times(self, node):
        left = self.evaluate(node.left)
        right = self.evaluate(node.right)

        attributes = []

        for attribute in left.attributes:
            attributes.append(
                Attribute(
                    attribute.name,
                    attribute.relation or left.name,
                    attribute.value_type
                )
            )

        for attribute in right.attributes:
            attributes.append(
                Attribute(
                    attribute.name,
                    attribute.relation or right.name,
                    attribute.value_type
                )
            )

        self.check_duplicate_qualified_names(attributes)

        result = Relation(
            f"{left.name}_times_{right.name}",
            attributes
        )

        for left_row in left.tuples:
            for right_row in right.tuples:
                result.add_tuple(
                    left_row.values + right_row.values
                )

        return result

    # ---------------------------------------------------------
    # Join
    # ---------------------------------------------------------

    def evaluate_join(self, node):
        left = self.evaluate(node.left)
        right = self.evaluate(node.right)

        product = self.evaluate_times_from_relations(
            left,
            right
        )

        result = product.copy_schema()

        for row in product.tuples:
            self.join_comparisons += 1

            if self.evaluate_condition(
                node.condition,
                product,
                row
            ):
                result.add_tuple(row.values)

        return result

    def evaluate_times_from_relations(self, left, right):
        attributes = []

        for attribute in left.attributes:
            attributes.append(
                Attribute(
                    attribute.name,
                    attribute.relation or left.name,
                    attribute.value_type
                )
            )

        for attribute in right.attributes:
            attributes.append(
                Attribute(
                    attribute.name,
                    attribute.relation or right.name,
                    attribute.value_type
                )
            )

        self.check_duplicate_qualified_names(attributes)

        result = Relation(
            f"{left.name}_times_{right.name}",
            attributes
        )

        for left_row in left.tuples:
            for right_row in right.tuples:
                result.add_tuple(
                    left_row.values + right_row.values
                )

        return result

    # ---------------------------------------------------------
    # Conditions
    # ---------------------------------------------------------

    def evaluate_condition(self, node, relation, row):

        if isinstance(node, AndNode):
            return (
                self.evaluate_condition(
                    node.left,
                    relation,
                    row
                )
                and
                self.evaluate_condition(
                    node.right,
                    relation,
                    row
                )
            )

        if isinstance(node, OrNode):
            return (
                self.evaluate_condition(
                    node.left,
                    relation,
                    row
                )
                or
                self.evaluate_condition(
                    node.right,
                    relation,
                    row
                )
            )

        if isinstance(node, NotNode):
            return not self.evaluate_condition(
                node.child,
                relation,
                row
            )

        if isinstance(node, ComparisonNode):
            left = self.resolve_operand(
                node.left,
                relation,
                row
            )

            right = self.resolve_operand(
                node.right,
                relation,
                row
            )

            return self.compare_values(
                left,
                node.operator,
                right
            )

        raise TypeErrorRA(
            "Invalid condition"
        )

    def resolve_operand(self, node, relation, row):

        if isinstance(node, NumberNode):
            return node.value

        if isinstance(node, StringNode):
            return node.value

        if isinstance(node, AttributeNode):
            index = relation.get_attribute_index(
                node.name,
                node.relation
            )

            return row.values[index]

        raise TypeErrorRA(
            "Invalid operand"
        )

    def compare_values(self, left, operator, right):

        left_type = self.get_value_type(left)
        right_type = self.get_value_type(right)

        if left_type != right_type:
            raise TypeErrorRA(
                f"Cannot compare {left_type} "
                f"with {right_type}"
            )

        if operator == "=":
            return left == right

        if operator == "!=":
            return left != right

        if operator == "<":
            return left < right

        if operator == "<=":
            return left <= right

        if operator == ">":
            return left > right

        if operator == ">=":
            return left >= right

        raise TypeErrorRA(
            f"Unknown comparison operator {operator}"
        )

    # ---------------------------------------------------------
    # Schema helpers
    # ---------------------------------------------------------

    def check_union_compatible(self, left, right):

        if len(left.attributes) != len(right.attributes):
            raise SchemaError(
                "Relations are not union compatible"
            )

        for i in range(len(left.attributes)):
            left_attr = left.attributes[i]
            right_attr = right.attributes[i]

            if left_attr.name != right_attr.name:
                raise SchemaError(
                    "Relations are not union compatible"
                )

            if (
                left_attr.value_type is not None
                and right_attr.value_type is not None
                and left_attr.value_type != right_attr.value_type
            ):
                raise SchemaError(
                    "Relations are not union compatible"
                )

    def check_duplicate_qualified_names(self, attributes):
        names = set()

        for attribute in attributes:
            name = attribute.qualified_name()

            if name in names:
                raise SchemaError(
                    f"Duplicate qualified attribute {name}"
                )

            names.add(name)

    def get_value_type(self, value):

        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return "number"

        if isinstance(value, str):
            return "string"

        raise TypeErrorRA(
            f"Unsupported value type "
            f"{type(value).__name__}"
        )