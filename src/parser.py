from .tokens import TokenType
from .errors import ParseError

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


class Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.position = 0

    def parse(self):
        """
        Parse a complete relational algebra expression.
        """
        expression = self.parse_expression()

        if not self.check(TokenType.EOF):
            token = self.current_token()

            raise ParseError(
                f"Unexpected token {token.value!r}",
                token.position
            )

        return expression

    # ---------------------------------------------------------
    # Relational expressions
    # ---------------------------------------------------------

    def parse_expression(self):
        return self.parse_union_expression()

    def parse_union_expression(self):
        """
        union and minus have the lowest precedence and
        associate from left to right.
        """
        left = self.parse_intersect_expression()

        while self.check_word("union") or self.check_word("minus"):
            operator = self.advance().value

            right = self.parse_intersect_expression()

            if operator == "union":
                left = UnionNode(left, right)
            else:
                left = MinusNode(left, right)

        return left

    def parse_intersect_expression(self):
        """
        intersect has higher precedence than union and minus.
        """
        left = self.parse_product_expression()

        while self.check_word("intersect"):
            self.advance()

            right = self.parse_product_expression()

            left = IntersectNode(left, right)

        return left

    def parse_product_expression(self):
        """
        times and join have higher precedence than
        intersect, union and minus.
        """
        left = self.parse_unary_expression()

        while self.check_word("times") or self.check_word("join"):

            if self.check_word("times"):
                self.advance()

                right = self.parse_unary_expression()

                left = TimesNode(left, right)

            else:
                # join[condition]
                self.advance()

                self.consume(
                    TokenType.LBRACKET,
                    "Expected '[' after join"
                )

                condition = self.parse_condition()

                self.consume(
                    TokenType.RBRACKET,
                    "Expected ']' after join condition"
                )

                right = self.parse_unary_expression()

                left = JoinNode(
                    condition,
                    left,
                    right
                )

        return left

    def parse_unary_expression(self):
        """
        Handles select, project and rename.
        """

        if self.check_word("select"):
            return self.parse_select()

        if self.check_word("project"):
            return self.parse_project()

        if self.check_word("rename"):
            return self.parse_rename()

        return self.parse_primary_expression()

    def parse_select(self):
        self.consume_word(
            "select",
            "Expected 'select'"
        )

        self.consume(
            TokenType.LBRACKET,
            "Expected '[' after select"
        )

        condition = self.parse_condition()

        self.consume(
            TokenType.RBRACKET,
            "Expected ']' after select condition"
        )

        self.consume(
            TokenType.LPAREN,
            "Expected '(' after select condition"
        )

        child = self.parse_expression()

        self.consume(
            TokenType.RPAREN,
            "Expected ')' after select expression"
        )

        return SelectNode(condition, child)

    def parse_project(self):
        self.consume_word(
            "project",
            "Expected 'project'"
        )

        self.consume(
            TokenType.LBRACKET,
            "Expected '[' after project"
        )

        # project[] is not allowed
        if self.check(TokenType.RBRACKET):
            raise ParseError(
                "Projection attribute list cannot be empty",
                self.current_token().position
            )

        attributes = self.parse_projection_list()

        self.consume(
            TokenType.RBRACKET,
            "Expected ']' after projection attributes"
        )

        self.consume(
            TokenType.LPAREN,
            "Expected '(' after projection attributes"
        )

        child = self.parse_expression()

        self.consume(
            TokenType.RPAREN,
            "Expected ')' after project expression"
        )

        return ProjectNode(attributes, child)

    def parse_rename(self):
        self.consume_word(
            "rename",
            "Expected 'rename'"
        )

        self.consume(
            TokenType.LBRACKET,
            "Expected '[' after rename"
        )

        name_token = self.consume(
            TokenType.WORD,
            "Expected new relation name"
        )

        self.consume(
            TokenType.RBRACKET,
            "Expected ']' after new relation name"
        )

        self.consume(
            TokenType.LPAREN,
            "Expected '(' after rename"
        )

        child = self.parse_expression()

        self.consume(
            TokenType.RPAREN,
            "Expected ')' after rename expression"
        )

        return RenameNode(
            name_token.value,
            child
        )

    def parse_primary_expression(self):
        """
        A primary expression is either:
        - a relation name
        - an expression inside parentheses
        """

        if self.match(TokenType.LPAREN):
            expression = self.parse_expression()

            self.consume(
                TokenType.RPAREN,
                "Expected ')' after expression"
            )

            return expression

        if self.check(TokenType.WORD):
            token = self.advance()

            return RelationNode(token.value)

        token = self.current_token()

        raise ParseError(
            "Expected relation name or expression",
            token.position
        )

    # ---------------------------------------------------------
    # Projection attributes
    # ---------------------------------------------------------

    def parse_projection_list(self):
        attributes = []

        attributes.append(
            self.parse_attribute_reference()
        )

        while self.match(TokenType.COMMA):
            attributes.append(
                self.parse_attribute_reference()
            )

        return attributes

    # ---------------------------------------------------------
    # Conditions
    # ---------------------------------------------------------

    def parse_condition(self):
        return self.parse_or_condition()

    def parse_or_condition(self):
        left = self.parse_and_condition()

        while self.check_word("or"):
            self.advance()

            right = self.parse_and_condition()

            left = OrNode(left, right)

        return left

    def parse_and_condition(self):
        left = self.parse_not_condition()

        while self.check_word("and"):
            self.advance()

            right = self.parse_not_condition()

            left = AndNode(left, right)

        return left

    def parse_not_condition(self):
        if self.check_word("not"):
            self.advance()

            child = self.parse_not_condition()

            return NotNode(child)

        return self.parse_condition_primary()

    def parse_condition_primary(self):
        # Parenthesized condition
        if self.match(TokenType.LPAREN):
            condition = self.parse_condition()

            self.consume(
                TokenType.RPAREN,
                "Expected ')' after condition"
            )

            return condition

        return self.parse_comparison()

    def parse_comparison(self):
        left = self.parse_operand()

        operator = self.parse_comparison_operator()

        right = self.parse_operand()

        return ComparisonNode(
            operator,
            left,
            right
        )

    def parse_comparison_operator(self):
        operators = {
            TokenType.EQUAL: "=",
            TokenType.NOT_EQUAL: "!=",
            TokenType.LESS: "<",
            TokenType.LESS_EQUAL: "<=",
            TokenType.GREATER: ">",
            TokenType.GREATER_EQUAL: ">="
        }

        token = self.current_token()

        if token.type not in operators:
            raise ParseError(
                "Expected comparison operator",
                token.position
            )

        self.advance()

        return operators[token.type]

    # ---------------------------------------------------------
    # Operands and attributes
    # ---------------------------------------------------------

    def parse_operand(self):
        token = self.current_token()

        if token.type == TokenType.NUMBER:
            self.advance()

            return NumberNode(token.value)

        if token.type == TokenType.STRING:
            self.advance()

            return StringNode(token.value)

        if token.type == TokenType.WORD:
            return self.parse_attribute_reference()

        raise ParseError(
            "Expected number, string or attribute",
            token.position
        )

    def parse_attribute_reference(self):
        first = self.consume(
            TokenType.WORD,
            "Expected attribute name"
        )

        # Qualified attribute such as Emp.DID
        if self.match(TokenType.DOT):
            second = self.consume(
                TokenType.WORD,
                "Expected attribute name after '.'"
            )

            return AttributeNode(
                second.value,
                first.value
            )

        return AttributeNode(first.value)

    # ---------------------------------------------------------
    # Helper methods
    # ---------------------------------------------------------

    def current_token(self):
        return self.tokens[self.position]

    def advance(self):
        token = self.current_token()

        if not self.check(TokenType.EOF):
            self.position += 1

        return token

    def check(self, token_type):
        return self.current_token().type == token_type

    def match(self, token_type):
        if self.check(token_type):
            self.advance()
            return True

        return False

    def check_word(self, word):
        token = self.current_token()

        return (
            token.type == TokenType.WORD
            and token.value.lower() == word.lower()
        )

    def consume(self, token_type, message):
        if self.check(token_type):
            return self.advance()

        token = self.current_token()

        raise ParseError(
            message,
            token.position
        )

    def consume_word(self, word, message):
        if self.check_word(word):
            return self.advance()

        token = self.current_token()

        raise ParseError(
            message,
            token.position
        )