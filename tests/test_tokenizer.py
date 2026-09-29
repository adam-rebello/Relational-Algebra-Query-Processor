import pytest

from src.tokenizer import Tokenizer
from src.tokens import TokenType
from src.errors import LexicalError


def get_tokens(text):
    """Tokenize text and remove EOF to make tests easier to read."""
    tokens = Tokenizer(text).tokenize()
    return tokens[:-1]


def test_no_whitespace():
    # Case 1: select[x1=3](R)
    tokens = get_tokens("select[x1=3](R)")

    assert [token.type for token in tokens] == [
        TokenType.WORD,
        TokenType.LBRACKET,
        TokenType.WORD,
        TokenType.EQUAL,
        TokenType.NUMBER,
        TokenType.RBRACKET,
        TokenType.LPAREN,
        TokenType.WORD,
        TokenType.RPAREN
    ]

    assert tokens[0].value == "select"
    assert tokens[2].value == "x1"
    assert tokens[4].value == 3
    assert tokens[7].value == "R"


def test_whitespace_same_tokens():
    # Case 2: whitespace should not change the tokens
    first = get_tokens("select[x1=3](R)")
    second = get_tokens("select[ x1 = 3 ](R)")

    assert [(t.type, t.value) for t in first] == [
        (t.type, t.value) for t in second
    ]


def test_greater_equal():
    # Case 3: >= must be one token
    tokens = get_tokens("select[Age>=30](R)")

    operators = [token for token in tokens
                 if token.type == TokenType.GREATER_EQUAL]

    assert len(operators) == 1
    assert operators[0].value == ">="


def test_negative_number():
    # Case 4: > and -30 must be separate tokens
    tokens = get_tokens("select[Age>-30](R)")

    assert any(
        token.type == TokenType.GREATER
        and token.value == ">"
        for token in tokens
    )

    assert any(
        token.type == TokenType.NUMBER
        and token.value == -30
        for token in tokens
    )


def test_parenthesis_inside_string():
    # Case 5: ) inside the string should stay in the string
    tokens = get_tokens("select[Name='Bob)'](R)")

    string_tokens = [
        token for token in tokens
        if token.type == TokenType.STRING
    ]

    assert len(string_tokens) == 1
    assert string_tokens[0].value == "Bob)"


def test_comma_inside_string():
    # Case 6: comma inside the string should not become a COMMA token
    tokens = get_tokens("select[Name='a,b'](R)")

    string_tokens = [
        token for token in tokens
        if token.type == TokenType.STRING
    ]

    assert len(string_tokens) == 1
    assert string_tokens[0].value == "a,b"


def test_doubled_quote_inside_string():
    # Case 7: two quotes inside a string represent one quote
    tokens = get_tokens("select[Name='O''Brien'](R)")

    string_tokens = [
        token for token in tokens
        if token.type == TokenType.STRING
    ]

    assert len(string_tokens) == 1
    assert string_tokens[0].value == "O'Brien"


def test_keyword_can_be_attribute():
    # Case 8: union is still scanned as a normal WORD
    tokens = get_tokens("select[union=3](R)")

    union_token = tokens[2]

    assert union_token.type == TokenType.WORD
    assert union_token.value == "union"


def test_unterminated_string():
    # Case 9: missing closing quote should be a lexical error
    with pytest.raises(LexicalError) as error:
        Tokenizer("select[Name='Bob](R)").tokenize()

    assert "Unterminated string" in str(error.value)
    assert error.value.position >= 0