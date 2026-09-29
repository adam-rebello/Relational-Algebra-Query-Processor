from .errors import SchemaError, TypeErrorRA


class Attribute:
    def __init__(self, name, relation=None, value_type=None):
        self.name = name
        self.relation = relation
        self.value_type = value_type

    def qualified_name(self):
        if self.relation:
            return f"{self.relation}.{self.name}"

        return self.name

    def __repr__(self):
        return self.qualified_name()


class RATuple:
    """
    Represents one tuple in a relation.
    """

    def __init__(self, values):
        self.values = list(values)

    def __eq__(self, other):
        if not isinstance(other, RATuple):
            return False

        if len(self.values) != len(other.values):
            return False

        for i in range(len(self.values)):
            if self.values[i] != other.values[i]:
                return False

        return True

    def __repr__(self):
        return f"({', '.join(str(v) for v in self.values)})"


class Relation:
    def __init__(self, name, attributes):
        self.name = name
        self.attributes = []

        for attribute in attributes:
            if isinstance(attribute, Attribute):
                self.attributes.append(attribute)
            else:
                self.attributes.append(
                    Attribute(attribute, relation=name)
                )

        self.tuples = []

    def add_tuple(self, values):
        """
        Add a tuple using set semantics.
        Duplicate tuples are ignored.
        """

        if len(values) != len(self.attributes):
            raise SchemaError(
                f"Relation {self.name} expects "
                f"{len(self.attributes)} values but received {len(values)}"
            )

        self._check_types(values)

        new_tuple = RATuple(values)

        for existing_tuple in self.tuples:
            if existing_tuple == new_tuple:
                return

        self.tuples.append(new_tuple)

    def _check_types(self, values):
        """
        The first value seen establishes the type of a column.
        Later values must match that type.
        """

        for i in range(len(values)):
            value = values[i]
            attribute = self.attributes[i]

            current_type = self._value_type(value)

            if attribute.value_type is None:
                attribute.value_type = current_type

            elif attribute.value_type != current_type:
                raise TypeErrorRA(
                    f"Attribute {attribute.qualified_name()} "
                    f"expects {attribute.value_type} values "
                    f"but received {current_type}"
                )

    def _value_type(self, value):
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return "number"

        if isinstance(value, str):
            return "string"

        raise TypeErrorRA(
            f"Unsupported value type: {type(value).__name__}"
        )

    def get_attribute_index(self, name, relation=None):
        """
        Find an attribute in the schema.
        Supports Age and Employees.Age.
        """

        matches = []

        for i, attribute in enumerate(self.attributes):
            if relation is not None:
                if (
                    attribute.relation == relation
                    and attribute.name == name
                ):
                    matches.append(i)

            elif attribute.name == name:
                matches.append(i)

        if len(matches) == 0:
            if relation:
                full_name = f"{relation}.{name}"
            else:
                full_name = name

            raise SchemaError(
                f"Unknown attribute {full_name}"
            )

        if len(matches) > 1:
            raise SchemaError(
                f"Ambiguous attribute {name}"
            )

        return matches[0]

    def copy_schema(self, name=None):
        """
        Make a new empty relation with the same schema.
        Keeps existing qualified attribute names.
        """

        relation_name = name if name is not None else self.name

        attributes = []

        for attribute in self.attributes:
            attributes.append(
                Attribute(
                    attribute.name,
                    attribute.relation,
                    attribute.value_type
                )
            )

        return Relation(relation_name, attributes)

    def schema_names(self):
        return [
            attribute.qualified_name()
            for attribute in self.attributes
        ]

    def __repr__(self):
        lines = []

        lines.append(
            f"{self.name}({', '.join(self.schema_names())})"
        )

        lines.append("{")

        for row in self.tuples:
            lines.append(
                "  " + ", ".join(str(v) for v in row.values)
            )

        lines.append("}")

        return "\n".join(lines)