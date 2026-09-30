import csv
import time

from src.relation import Relation
from src.tokenizer import Tokenizer
from src.parser import Parser
from src.evaluator import Evaluator


SIZE = 4000

MATCH_RATES = [
    1,
    2,
    4,
    8
]


def make_relations(size, match_rate):
    r = Relation("R", ["a", "b"])
    s = Relation("S", ["b", "c"])

    for i in range(size):
        r.add_tuple([
            i,
            i // match_rate
        ])

    for i in range(size):
        s.add_tuple([
            i // match_rate,
            i
        ])

    return r, s


def parse_query(query):
    tokens = Tokenizer(query).tokenize()
    return Parser(tokens).parse()


def benchmark_match_rate(match_rate):
    r, s = make_relations(
        SIZE,
        match_rate
    )

    tree = parse_query(
        "R join[R.b=S.b] S"
    )

    evaluator = Evaluator({
        "R": r,
        "S": s
    })

    start = time.perf_counter()

    result = evaluator.evaluate(tree)

    end = time.perf_counter()

    return {
        "match_rate": match_rate,
        "size": SIZE,
        "comparisons": evaluator.join_comparisons,
        "wall_time": end - start,
        "output_tuples": len(result.tuples)
    }


def main():
    results = []

    for match_rate in MATCH_RATES:
        print(
            f"\nRunning match rate {match_rate}..."
        )

        result = benchmark_match_rate(
            match_rate
        )

        results.append(result)

        print(
            f"Comparisons: "
            f"{result['comparisons']}"
        )

        print(
            f"Wall time: "
            f"{result['wall_time']:.6f} seconds"
        )

        print(
            f"Output tuples: "
            f"{result['output_tuples']}"
        )

    with open(
        "performance_match_rate_results.csv",
        "w",
        newline="",
        encoding="utf-8"
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=[
                "match_rate",
                "size",
                "comparisons",
                "wall_time",
                "output_tuples"
            ]
        )

        writer.writeheader()
        writer.writerows(results)

    print(
        "\nResults saved to "
        "performance_match_rate_results.csv"
    )


if __name__ == "__main__":
    main()