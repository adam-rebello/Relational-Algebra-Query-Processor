from enum import Enum


class TokenType(Enum):
    WORD = "WORD"
    NUMBER = "NUMBER"
    STRING = "STRING"

    LPAREN = "("
    RPAREN = ")"
    LBRACKET = "["
    RBRACKET = "]"
    LBRACE = "{"
    RBRACE = "}"
    COMMA = ","
    DOT = "."

    EQUAL = "="
    NOT_EQUAL = "!="
    LESS = "<"
    LESS_EQUAL = "<="
    GREATER = ">"
    GREATER_EQUAL = ">="

    EOF = "EOF"


class Token:
    def __init__(self, token_type, value, position):
        self.type = token_type
        self.value = value
        self.position = position

    def __repr__(self):
        return f"Token({self.type.name}, {self.value!r}, pos={self.position})"