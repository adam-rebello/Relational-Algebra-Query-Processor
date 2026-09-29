from .tokens import Token, TokenType
from .errors import LexicalError


class Tokenizer:
    def __init__(self, text):
        self.text = text
        self.position = 0
        self.tokens = []

    def tokenize(self):
        while not self.is_at_end():
            char = self.current_char()

            # Ignore normal whitespace
            if char.isspace():
                self.advance()
                continue

            # Comments start with //
            if char == "/" and self.peek() == "/":
                self.skip_comment()
                continue

            # Words / identifiers
            if char.isalpha() or char == "_":
                self.tokens.append(self.scan_word())
                continue

            # Numbers, including negative numbers
            if char.isdigit() or (char == "-" and self.peek().isdigit()):
                self.tokens.append(self.scan_number())
                continue

            # Quoted strings
            if char == "'":
                self.tokens.append(self.scan_string())
                continue

            # Single-character punctuation
            if char == "(":
                self.add_simple_token(TokenType.LPAREN)
            elif char == ")":
                self.add_simple_token(TokenType.RPAREN)
            elif char == "[":
                self.add_simple_token(TokenType.LBRACKET)
            elif char == "]":
                self.add_simple_token(TokenType.RBRACKET)
            elif char == "{":
                self.add_simple_token(TokenType.LBRACE)
            elif char == "}":
                self.add_simple_token(TokenType.RBRACE)
            elif char == ",":
                self.add_simple_token(TokenType.COMMA)
            elif char == ".":
                self.add_simple_token(TokenType.DOT)

            # Comparison operators
            elif char == "=":
                self.add_simple_token(TokenType.EQUAL)

            elif char == "!":
                self.scan_not_equal()

            elif char == ">":
                self.scan_greater()

            elif char == "<":
                self.scan_less()

            else:
                raise LexicalError(
                    f"Unexpected character {char!r}",
                    self.position
                )

        self.tokens.append(
            Token(TokenType.EOF, None, self.position)
        )

        return self.tokens

    def current_char(self):
        return self.text[self.position]

    def peek(self):
        if self.position + 1 >= len(self.text):
            return "\0"

        return self.text[self.position + 1]

    def advance(self):
        self.position += 1

    def is_at_end(self):
        return self.position >= len(self.text)

    def add_simple_token(self, token_type):
        start = self.position
        value = self.current_char()

        self.tokens.append(
            Token(token_type, value, start)
        )

        self.advance()

    def scan_word(self):
        start = self.position

        while not self.is_at_end():
            char = self.current_char()

            if char.isalnum() or char == "_":
                self.advance()
            else:
                break

        value = self.text[start:self.position]

        return Token(
            TokenType.WORD,
            value,
            start
        )

    def scan_number(self):
        start = self.position

        # Optional negative sign
        if self.current_char() == "-":
            self.advance()

        while not self.is_at_end() and self.current_char().isdigit():
            self.advance()

        # Optional decimal part
        if (
            not self.is_at_end()
            and self.current_char() == "."
            and self.peek().isdigit()
        ):
            self.advance()

            while (
                not self.is_at_end()
                and self.current_char().isdigit()
            ):
                self.advance()

        text_value = self.text[start:self.position]

        if "." in text_value:
            value = float(text_value)
        else:
            value = int(text_value)

        return Token(
            TokenType.NUMBER,
            value,
            start
        )

    def scan_string(self):
        start = self.position

        # Skip opening quote
        self.advance()

        characters = []

        while not self.is_at_end():
            char = self.current_char()

            if char == "'":
                # Two single quotes represent one literal quote
                if self.peek() == "'":
                    characters.append("'")
                    self.advance()
                    self.advance()
                    continue

                # Closing quote
                self.advance()

                return Token(
                    TokenType.STRING,
                    "".join(characters),
                    start
                )

            characters.append(char)
            self.advance()

        raise LexicalError(
            "Unterminated string",
            start
        )

    def scan_greater(self):
        start = self.position

        self.advance()

        if not self.is_at_end() and self.current_char() == "=":
            self.advance()

            self.tokens.append(
                Token(
                    TokenType.GREATER_EQUAL,
                    ">=",
                    start
                )
            )
        else:
            self.tokens.append(
                Token(
                    TokenType.GREATER,
                    ">",
                    start
                )
            )

    def scan_less(self):
        start = self.position

        self.advance()

        if not self.is_at_end() and self.current_char() == "=":
            self.advance()

            self.tokens.append(
                Token(
                    TokenType.LESS_EQUAL,
                    "<=",
                    start
                )
            )
        else:
            self.tokens.append(
                Token(
                    TokenType.LESS,
                    "<",
                    start
                )
            )

    def scan_not_equal(self):
        start = self.position

        self.advance()

        if not self.is_at_end() and self.current_char() == "=":
            self.advance()

            self.tokens.append(
                Token(
                    TokenType.NOT_EQUAL,
                    "!=",
                    start
                )
            )

            return

        raise LexicalError(
            "Expected '=' after '!'",
            start
        )

    def skip_comment(self):
        while (
            not self.is_at_end()
            and self.current_char() != "\n"
        ):
            self.advance()