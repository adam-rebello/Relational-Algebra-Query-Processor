import pytest

from src.relation import Relation
from src.errors import SchemaError, TypeErrorRA


def test_add_tuple():
    relation = Relation(
        "Employees",
        ["EID", "Name", "Age", "DID"]
    )

    relation.add_tuple(
        ["E1", "John", 32, "D1"]
    )

    assert len(relation.tuples) == 1


def test_duplicate_tuple_removed():
    relation = Relation(
        "Employees",
        ["EID", "Name", "Age", "DID"]
    )

    relation.add_tuple(
        ["E1", "John", 32, "D1"]
    )

    relation.add_tuple(
        ["E1", "John", 32, "D1"]
    )

    assert len(relation.tuples) == 1


def test_wrong_number_of_values():
    relation = Relation(
        "R",
        ["A", "B"]
    )

    with pytest.raises(SchemaError):
        relation.add_tuple([1])


def test_type_tracking():
    relation = Relation(
        "R",
        ["A"]
    )

    relation.add_tuple([1])
    relation.add_tuple([2.5])

    assert relation.attributes[0].value_type == "number"


def test_incompatible_column_type():
    relation = Relation(
        "R",
        ["A"]
    )

    relation.add_tuple([1])

    with pytest.raises(TypeErrorRA):
        relation.add_tuple(["hello"])


def test_attribute_lookup():
    relation = Relation(
        "Employees",
        ["EID", "Name", "Age"]
    )

    assert relation.get_attribute_index("Age") == 2


def test_qualified_attribute_lookup():
    relation = Relation(
        "Employees",
        ["EID", "Name", "Age"]
    )

    assert (
        relation.get_attribute_index(
            "Age",
            "Employees"
        )
        == 2
    )