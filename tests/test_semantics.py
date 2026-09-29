import pytest

from src.tokenizer import Tokenizer
from src.parser import Parser
from src.evaluator import Evaluator
from src.relation import Relation
from src.errors import SchemaError, TypeErrorRA


def parse_query(text):
    tokens = Tokenizer(text).tokenize()
    return Parser(tokens).parse()


def run_query(text, relations):
    tree = parse_query(text)
    evaluator = Evaluator(relations)
    return evaluator.evaluate(tree)


# ---------------------------------------------------------
# Case 18
# select[A=B](R)
# Both sides must be treated as attributes.
# ---------------------------------------------------------

def test_case18_attribute_to_attribute_comparison():
    relation = Relation("R", ["A", "B"])

    relation.add_tuple([1, 1])
    relation.add_tuple([1, 2])
    relation.add_tuple([3, 3])

    result = run_query(
        "select[A=B](R)",
        {"R": relation}
    )

    assert len(result.tuples) == 2
    assert result.tuples[0].values == [1, 1]
    assert result.tuples[1].values == [3, 3]


# ---------------------------------------------------------
# Case 19
# Qualified names in a join
# ---------------------------------------------------------

def test_case19_qualified_names_in_join():
    emp = Relation(
        "Emp",
        ["EID", "Name", "DID"]
    )

    emp.add_tuple(["E1", "John", "D1"])
    emp.add_tuple(["E2", "Alice", "D2"])

    dept = Relation(
        "Dept",
        ["DID", "DeptName"]
    )

    dept.add_tuple(["D1", "Sales"])
    dept.add_tuple(["D2", "IT"])

    result = run_query(
        "Emp join[Emp.DID=Dept.DID] Dept",
        {
            "Emp": emp,
            "Dept": dept
        }
    )

    assert len(result.tuples) == 2

    # Both DID columns must remain distinguishable
    assert "Emp.DID" in result.schema_names()
    assert "Dept.DID" in result.schema_names()


# ---------------------------------------------------------
# Case 20
# Self join using rename
# ---------------------------------------------------------

def test_case20_self_join_with_rename():
    emp = Relation(
        "Emp",
        ["EID", "MgrID"]
    )

    emp.add_tuple(["E1", "E2"])
    emp.add_tuple(["E2", "E3"])
    emp.add_tuple(["E3", "E3"])

    result = run_query(
        "rename[E2](Emp) "
        "join[Emp.MgrID=E2.EID] Emp",
        {"Emp": emp}
    )

    assert len(result.tuples) == 3

    # The renamed relation and original relation
    # must have different qualified names.
    assert "E2.EID" in result.schema_names()
    assert "Emp.EID" in result.schema_names()


# ---------------------------------------------------------
# Case 21
# Union with different schemas must fail
# ---------------------------------------------------------

def test_case21_incompatible_union():
    r = Relation("R", ["A"])
    r.add_tuple([1])

    s = Relation("S", ["B"])
    s.add_tuple([1])

    with pytest.raises(SchemaError):
        run_query(
            "R union S",
            {
                "R": r,
                "S": s
            }
        )


# ---------------------------------------------------------
# Case 22
# Comparing a number to a string must be a type error
# ---------------------------------------------------------

def test_case22_number_string_type_error():
    r = Relation("R", ["Age"])
    r.add_tuple([30])
    r.add_tuple([40])

    with pytest.raises(TypeErrorRA):
        run_query(
            "select[Age>'30'](R)",
            {"R": r}
        )


# ---------------------------------------------------------
# Case 23
# Projection must remove duplicates
# ---------------------------------------------------------

def test_case23_projection_removes_duplicates():
    employees = Relation(
        "Employees",
        ["EID", "Name", "Age", "DID"]
    )

    employees.add_tuple(
        ["E1", "John", 32, "D1"]
    )

    employees.add_tuple(
        ["E2", "Alice", 28, "D2"]
    )

    employees.add_tuple(
        ["E3", "Bob", 29, "D1"]
    )

    result = run_query(
        "project[DID](Employees)",
        {"Employees": employees}
    )

    assert len(result.tuples) == 2

    values = [
        row.values[0]
        for row in result.tuples
    ]

    assert "D1" in values
    assert "D2" in values


# ---------------------------------------------------------
# Case 24
# Duplicate projection attribute
# Our documented rule: schema error
# ---------------------------------------------------------

def test_case24_duplicate_projection_attribute():
    r = Relation(
        "R",
        ["Name", "Age"]
    )

    r.add_tuple(["John", 30])

    with pytest.raises(SchemaError):
        run_query(
            "project[Name,Name](R)",
            {"R": r}
        )


# ---------------------------------------------------------
# Case 25
# An empty result must still preserve its schema
# ---------------------------------------------------------

def test_case25_empty_result_preserves_schema():
    r = Relation(
        "R",
        ["Age", "Name"]
    )

    r.add_tuple([20, "John"])
    r.add_tuple([25, "Alice"])

    result = run_query(
        "select[Age>100](R)",
        {"R": r}
    )

    assert len(result.tuples) == 0

    assert result.schema_names() == [
        "R.Age",
        "R.Name"
    ]