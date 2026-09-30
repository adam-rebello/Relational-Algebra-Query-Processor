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
        self.relations = relations

        # Performance counters required by the assignment
        self.join_comparisons = 0
        self.select_comparisons = 0

    # ---------------------------------------------------------
    # Main evaluator
    # ---------------------------------------------------------

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

            # Our documented rule:
            # duplicate projection attributes are an error
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

            original_attribute = relation.attributes[index]

            attributes.append(
                Attribute(
                    original_attribute.name,
                    original_attribute.relation,
                    original_attribute.value_type
                )
            )

        result = Relation(
            relation.name,
            attributes
        )

        for row in relation.tuples:
            values = [
                row.values[index]
                for index in indexes
            ]

            # add_tuple removes duplicate projected tuples
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
    # Union
    # ---------------------------------------------------------

    def evaluate_union(self, node):
        left = self.evaluate(node.left)
        right = self.evaluate(node.right)

        self.check_union_compatible(
            left,
            right
        )

        result = left.copy_schema()

        for row in left.tuples:
            result.add_tuple(row.values)

        for row in right.tuples:
            result.add_tuple(row.values)

        return result

    # ---------------------------------------------------------
    # Intersect
    # ---------------------------------------------------------

    def evaluate_intersect(self, node):
        left = self.evaluate(node.left)
        right = self.evaluate(node.right)

        self.check_union_compatible(
            left,
            right
        )

        result = left.copy_schema()

        for left_row in left.tuples:
            for right_row in right.tuples:
                if left_row == right_row:
                    result.add_tuple(
                        left_row.values
                    )
                    break

        return result

    # ---------------------------------------------------------
    # Minus
    # ---------------------------------------------------------

    def evaluate_minus(self, node):
        left = self.evaluate(node.left)
        right = self.evaluate(node.right)

        self.check_union_compatible(
            left,
            right
        )

        result = left.copy_schema()

        for left_row in left.tuples:
            found = False

            for right_row in right.tuples:
                if left_row == right_row:
                    found = True
                    break

            if not found:
                result.add_tuple(
                    left_row.values
                )

        return result

    # ---------------------------------------------------------
    # Cartesian Product
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

        self.check_duplicate_qualified_names(
            attributes
        )

        result = Relation(
            f"{left.name}_times_{right.name}",
            attributes
        )

        for left_row in left.tuples:
            for right_row in right.tuples:
                combined_values = (
                    left_row.values
                    + right_row.values
                )

                result.add_tuple(
                    combined_values
                )

        return result

    # ---------------------------------------------------------
    # Join
    # ---------------------------------------------------------

    def evaluate_join(self, node):
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

        self.check_duplicate_qualified_names(
            attributes
        )

        result = Relation(
            f"{left.name}_join_{right.name}",
            attributes
        )

        # Nested-loop theta join.
        # Every left/right pair is checked.
        for left_row in left.tuples:
            for right_row in right.tuples:
                self.join_comparisons += 1

                if self.evaluate_join_condition(
                    node.condition,
                    left,
                    left_row,
                    right,
                    right_row
                ):
                    result.add_tuple(
                        left_row.values
                        + right_row.values
                    )

        return result

    # ---------------------------------------------------------
    # Join Conditions
    # ---------------------------------------------------------

    def evaluate_join_condition(
        self,
        node,
        left_relation,
        left_row,
        right_relation,
        right_row
    ):
        if isinstance(node, AndNode):
            return (
                self.evaluate_join_condition(
                    node.left,
                    left_relation,
                    left_row,
                    right_relation,
                    right_row
                )
                and
                self.evaluate_join_condition(
                    node.right,
                    left_relation,
                    left_row,
                    right_relation,
                    right_row
                )
            )

        if isinstance(node, OrNode):
            return (
                self.evaluate_join_condition(
                    node.left,
                    left_relation,
                    left_row,
                    right_relation,
                    right_row
                )
                or
                self.evaluate_join_condition(
                    node.right,
                    left_relation,
                    left_row,
                    right_relation,
                    right_row
                )
            )

        if isinstance(node, NotNode):
            return not self.evaluate_join_condition(
                node.child,
                left_relation,
                left_row,
                right_relation,
                right_row
            )

        if isinstance(node, ComparisonNode):
            left_value = self.resolve_join_operand(
                node.left,
                left_relation,
                left_row,
                right_relation,
                right_row
            )

            right_value = self.resolve_join_operand(
                node.right,
                left_relation,
                left_row,
                right_relation,
                right_row
            )

            return self.compare_values(
                left_value,
                node.operator,
                right_value
            )

        raise TypeErrorRA(
            "Invalid join condition"
        )

    def resolve_join_operand(
        self,
        node,
        left_relation,
        left_row,
        right_relation,
        right_row
    ):
        if isinstance(node, NumberNode):
            return node.value

        if isinstance(node, StringNode):
            return node.value

        if not isinstance(node, AttributeNode):
            raise TypeErrorRA(
                "Invalid join operand"
            )

        matches = []

        # Qualified attribute:
        # Emp.DID, Dept.DID, E2.EID, etc.
        if node.relation is not None:

            for index, attribute in enumerate(
                left_relation.attributes
            ):
                relation_name = (
                    attribute.relation
                    or left_relation.name
                )

                if (
                    relation_name == node.relation
                    and attribute.name == node.name
                ):
                    matches.append(
                        ("left", index)
                    )

            for index, attribute in enumerate(
                right_relation.attributes
            ):
                relation_name = (
                    attribute.relation
                    or right_relation.name
                )

                if (
                    relation_name == node.relation
                    and attribute.name == node.name
                ):
                    matches.append(
                        ("right", index)
                    )

            if len(matches) == 0:
                raise SchemaError(
                    f"Unknown attribute "
                    f"{node.relation}.{node.name}"
                )

            if len(matches) > 1:
                raise SchemaError(
                    f"Ambiguous attribute "
                    f"{node.relation}.{node.name}"
                )

        # Unqualified attribute:
        # DID, Age, Name, etc.
        else:
            for index, attribute in enumerate(
                left_relation.attributes
            ):
                if attribute.name == node.name:
                    matches.append(
                        ("left", index)
                    )

            for index, attribute in enumerate(
                right_relation.attributes
            ):
                if attribute.name == node.name:
                    matches.append(
                        ("right", index)
                    )

            if len(matches) == 0:
                raise SchemaError(
                    f"Unknown attribute {node.name}"
                )

            if len(matches) > 1:
                raise SchemaError(
                    f"Ambiguous attribute {node.name}"
                )

        side, index = matches[0]

        if side == "left":
            return left_row.values[index]

        return right_row.values[index]

    # ---------------------------------------------------------
    # Normal Selection Conditions
    # ---------------------------------------------------------

    def evaluate_condition(
        self,
        node,
        relation,
        row
    ):
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

    # ---------------------------------------------------------
    # Normal Operand Resolution
    # ---------------------------------------------------------

    def resolve_operand(
        self,
        node,
        relation,
        row
    ):
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

    # ---------------------------------------------------------
    # Comparison
    # ---------------------------------------------------------

    def compare_values(
        self,
        left,
        operator,
        right
    ):
        left_type = self.get_value_type(
            left
        )

        right_type = self.get_value_type(
            right
        )

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
            f"Unknown comparison operator "
            f"{operator}"
        )

    # ---------------------------------------------------------
    # Union Compatibility
    # ---------------------------------------------------------

    def check_union_compatible(
        self,
        left,
        right
    ):
        if len(left.attributes) != len(
            right.attributes
        ):
            raise SchemaError(
                "Relations are not union compatible"
            )

        for index in range(
            len(left.attributes)
        ):
            left_attribute = (
                left.attributes[index]
            )

            right_attribute = (
                right.attributes[index]
            )

            if (
                left_attribute.name
                != right_attribute.name
            ):
                raise SchemaError(
                    "Relations are not union compatible"
                )

            if (
                left_attribute.value_type is not None
                and
                right_attribute.value_type is not None
                and
                left_attribute.value_type
                != right_attribute.value_type
            ):
                raise SchemaError(
                    "Relations are not union compatible"
                )

    # ---------------------------------------------------------
    # Qualified Name Collision Check
    # ---------------------------------------------------------

    def check_duplicate_qualified_names(
        self,
        attributes
    ):
        names = set()

        for attribute in attributes:
            name = attribute.qualified_name()

            if name in names:
                raise SchemaError(
                    f"Duplicate qualified attribute "
                    f"{name}"
                )

            names.add(name)

    # ---------------------------------------------------------
    # Value Types
    # ---------------------------------------------------------

    def get_value_type(self, value):
        if (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
        ):
            return "number"

        if isinstance(value, str):
            return "string"

        raise TypeErrorRA(
            f"Unsupported value type "
            f"{type(value).__name__}"
        )