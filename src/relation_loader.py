from .relation import Relation
from .errors import ParseError


class RelationLoader:
    def __init__(self, text):
        self.lines = text.splitlines()

    def load(self):
        relations = {}
        line_number = 0

        while line_number < len(self.lines):
            line = self.lines[line_number].strip()

            # Ignore blank lines and comments
            if not line or line.startswith("//"):
                line_number += 1
                continue

            name, attributes = self.parse_header(line, line_number)

            if name in relations:
                raise ParseError(
                    f"Relation {name} is already defined",
                    line_number
                )

            relation = Relation(name, attributes)
            line_number += 1

            found_end = False

            while line_number < len(self.lines):
                line = self.lines[line_number].strip()

                if not line or line.startswith("//"):
                    line_number += 1
                    continue

                if line == "}":
                    found_end = True
                    line_number += 1
                    break

                values = self.parse_tuple(line, line_number)
                relation.add_tuple(values)

                line_number += 1

            if not found_end:
                raise ParseError(
                    f"Missing '}}' for relation {name}",
                    line_number
                )

            relations[name] = relation

        return relations

    def parse_header(self, line, position):
        open_paren = line.find("(")
        close_paren = line.find(")")
        equals = line.find("=")
        brace = line.find("{")

        if (
            open_paren == -1
            or close_paren == -1
            or equals == -1
            or brace == -1
        ):
            raise ParseError(
                "Invalid relation definition",
                position
            )

        if not (
            open_paren < close_paren < equals < brace
        ):
            raise ParseError(
                "Invalid relation definition",
                position
            )

        name = line[:open_paren].strip()

        if not self.valid_identifier(name):
            raise ParseError(
                f"Invalid relation name {name!r}",
                position
            )

        attribute_text = line[
            open_paren + 1:close_paren
        ]

        attributes = []

        for part in attribute_text.split(","):
            attribute = part.strip()

            if not attribute:
                raise ParseError(
                    "Empty attribute name",
                    position
                )

            if not self.valid_identifier(attribute):
                raise ParseError(
                    f"Invalid attribute name {attribute!r}",
                    position
                )

            if attribute in attributes:
                raise ParseError(
                    f"Duplicate attribute {attribute}",
                    position
                )

            attributes.append(attribute)

        if not attributes:
            raise ParseError(
                "Relation must contain at least one attribute",
                position
            )

        return name, attributes

    def parse_tuple(self, line, position):
        parts = self.split_values(line, position)

        values = []

        for part in parts:
            values.append(
                self.parse_value(part, position)
            )

        return values

    def split_values(self, line, position):
        values = []
        current = []
        index = 0
        in_string = False

        while index < len(line):
            char = line[index]

            if char == "'":
                current.append(char)

                if in_string:
                    # Two quotes inside a string = literal quote
                    if (
                        index + 1 < len(line)
                        and line[index + 1] == "'"
                    ):
                        current.append("'")
                        index += 2
                        continue

                    in_string = False

                else:
                    in_string = True

                index += 1
                continue

            if char == "," and not in_string:
                values.append(
                    "".join(current).strip()
                )
                current = []
                index += 1
                continue

            current.append(char)
            index += 1

        if in_string:
            raise ParseError(
                "Unterminated string in relation data",
                position
            )

        values.append(
            "".join(current).strip()
        )

        if any(value == "" for value in values):
            raise ParseError(
                "Tuple contains an empty value",
                position
            )

        return values

    def parse_value(self, text, position):
        # Quoted string
        if text.startswith("'"):
            if not text.endswith("'") or len(text) < 2:
                raise ParseError(
                    "Invalid quoted string",
                    position
                )

            inside = text[1:-1]
            value = ""
            index = 0

            while index < len(inside):
                if (
                    inside[index] == "'"
                    and index + 1 < len(inside)
                    and inside[index + 1] == "'"
                ):
                    value += "'"
                    index += 2
                else:
                    value += inside[index]
                    index += 1

            return value

        # Number
        if self.is_number(text):
            if "." in text:
                return float(text)

            return int(text)

        # Bare string
        return text

    def is_number(self, text):
        if not text:
            return False

        index = 0
        decimal_seen = False
        digit_seen = False

        if text[0] == "-":
            index = 1

        while index < len(text):
            char = text[index]

            if char.isdigit():
                digit_seen = True

            elif char == "." and not decimal_seen:
                decimal_seen = True

            else:
                return False

            index += 1

        return digit_seen

    def valid_identifier(self, text):
        if not text:
            return False

        if not (
            text[0].isalpha()
            or text[0] == "_"
        ):
            return False

        for char in text[1:]:
            if not (
                char.isalnum()
                or char == "_"
            ):
                return False

        return True