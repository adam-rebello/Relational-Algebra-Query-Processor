import csv
import time

from src.relation import Relation
from src.tokenizer import Tokenizer
from src.parser import Parser
from src.evaluator import Evaluator


SIZES = [
    16000,
    32000,
    64000
]


def make_relations(size, match_rate=1):
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


def benchmark_join(size, match_rate=1):
    r, s = make_relations(
        size,
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
        "n": size,
        "m": size,
        "comparisons": evaluator.join_comparisons,
        "wall_time": end - start,
        "output_tuples": len(result.tuples)
    }


def main():
    results = []

    for size in SIZES:
        print(
            f"\nRunning join with "
            f"{size} x {size} tuples..."
        )

        result = benchmark_join(size)

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

        # Save after every completed run
        # so earlier results are not lost.
        with open(
            "performance_results_remaining.csv",
            "w",
            newline="",
            encoding="utf-8"
        ) as file:

            writer = csv.DictWriter(
                file,
                fieldnames=[
                    "n",
                    "m",
                    "comparisons",
                    "wall_time",
                    "output_tuples"
                ]
            )

            writer.writeheader()
            writer.writerows(results)

    print(
        "\nRemaining benchmark results saved to "
        "performance_results_remaining.csv"
    )


if __name__ == "__main__":
    main()