import argparse
import sys

from src.tokenizer import Tokenizer
from src.parser import Parser
from src.evaluator import Evaluator
from src.relation_loader import RelationLoader
from src.tree_printer import print_tree
from src.errors import RAError


def parse_query(query):
    tokens = Tokenizer(query).tokenize()
    return Parser(tokens).parse()


def load_relations(filename):
    with open(filename, "r", encoding="utf-8") as file:
        text = file.read()

    return RelationLoader(text).load()


def format_relation(relation):
    lines = []

    schema = ", ".join(
        relation.schema_names()
    )

    lines.append(
        f"{relation.name}({schema})"
    )

    lines.append("{")

    for row in relation.tuples:
        values = ", ".join(
            str(value)
            for value in row.values
        )

        lines.append(f"  {values}")

    lines.append("}")

    return "\n".join(lines)


def main():
    argument_parser = argparse.ArgumentParser(
        description="Relational Algebra Query Processor"
    )

    argument_parser.add_argument(
        "--tree",
        action="store_true",
        help="Print the parse tree without executing the query"
    )

    argument_parser.add_argument(
        "--data",
        help="File containing relation definitions"
    )

    argument_parser.add_argument(
        "query",
        help="Relational algebra query"
    )

    args = argument_parser.parse_args()

    try:
        tree = parse_query(args.query)

        if args.tree:
            print(print_tree(tree))
            return

        if args.data is None:
            print(
                "Error: --data is required when executing a query"
            )
            return

        relations = load_relations(args.data)

        evaluator = Evaluator(relations)
        result = evaluator.evaluate(tree)

        print(format_relation(result))

        if evaluator.join_comparisons > 0:
            print(
                f"\nJoin comparisons: "
                f"{evaluator.join_comparisons}"
            )

        if evaluator.select_comparisons > 0:
            print(
                f"Selection examinations: "
                f"{evaluator.select_comparisons}"
            )

    except RAError as error:
        print(f"Error: {error}")

    except FileNotFoundError:
        print(
            f"Error: data file {args.data!r} was not found"
        )

    except Exception as error:
        # During development this prevents the CLI from
        # displaying a Python traceback to the user.
        print(f"Error: {error}")


if __name__ == "__main__":
    main()