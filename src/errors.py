class RAError(Exception):
    """Base error for the relational algebra engine."""
    pass


class LexicalError(RAError):
    def __init__(self, message, position):
        self.message = message
        self.position = position
        super().__init__(f"{message} at position {position}")


class ParseError(RAError):
    def __init__(self, message, position):
        self.message = message
        self.position = position
        super().__init__(f"{message} at position {position}")


class NameErrorRA(RAError):
    pass


class SchemaError(RAError):
    pass


class TypeErrorRA(RAError):
    pass