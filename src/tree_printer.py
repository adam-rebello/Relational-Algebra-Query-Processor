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
    ComparisonNode
)


def print_tree(node):
    lines = []

    build_tree(node, "", True, lines)

    return "\n".join(lines)


def build_tree(node, prefix, is_last, lines):
    connector = "└── " if is_last else "├── "

    lines.append(
        prefix + connector + node_label(node)
    )

    children = get_children(node)

    if not children:
        return

    child_prefix = prefix + (
        "    " if is_last else "│   "
    )

    for index, child in enumerate(children):
        build_tree(
            child,
            child_prefix,
            index == len(children) - 1,
            lines
        )


def node_label(node):
    if isinstance(node, RelationNode):
        return f"Relation({node.name})"

    if isinstance(node, SelectNode):
        return f"Select(cond={node.condition})"

    if isinstance(node, ProjectNode):
        attrs = ", ".join(
            str(attribute)
            for attribute in node.attributes
        )

        return f"Project(attrs=[{attrs}])"

    if isinstance(node, RenameNode):
        return f"Rename({node.new_name})"

    if isinstance(node, JoinNode):
        return f"Join(cond={node.condition})"

    return str(node)


def get_children(node):
    if isinstance(
        node,
        (
            UnionNode,
            IntersectNode,
            MinusNode,
            TimesNode,
            AndNode,
            OrNode
        )
    ):
        return [node.left, node.right]

    if isinstance(node, JoinNode):
        return [
            node.condition,
            node.left,
            node.right
        ]

    if isinstance(
        node,
        (
            SelectNode,
            ProjectNode,
            RenameNode
        )
    ):
        return [node.child]

    if isinstance(node, NotNode):
        return [node.child]

    if isinstance(node, ComparisonNode):
        return [node.left, node.right]

    return []