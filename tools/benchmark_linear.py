import csv
import time

from src.relation import Relation
from src.tokenizer import Tokenizer
from src.parser import Parser
from src.evaluator import Evaluator


SIZES = [
    1000,
    2000,
    4000,
    8000,
    16000,
    32000,
    64000
]


def make_relation(size):
    r = Relation("R", ["a", "b"])

    for i in range(size):
        r.add_tuple([
            i,
            i % 10
        ])

    return r


def parse_query(query):
    tokens = Tokenizer(query).tokenize()
    return Parser(tokens).parse()


def benchmark_select(size):
    r = make_relation(size)

    tree = parse_query(
        "select[a<0](R)"
    )

    evaluator = Evaluator({
        "R": r
    })

    start = time.perf_counter()

    result = evaluator.evaluate(tree)

    end = time.perf_counter()

    return {
        "operator": "select",
        "size": size,
        "counter": evaluator.select_comparisons,
        "wall_time": end - start,
        "output_tuples": len(result.tuples)
    }


def benchmark_project(size):
    r = make_relation(size)

    tree = parse_query(
        "project[b](R)"
    )

    evaluator = Evaluator({
        "R": r
    })

    start = time.perf_counter()

    result = evaluator.evaluate(tree)

    end = time.perf_counter()

    return {
        "operator": "project",
        "size": size,
        "counter": "",
        "wall_time": end - start,
        "output_tuples": len(result.tuples)
    }


def main():
    results = []

    for size in SIZES:
        print(
            f"\nRunning select with {size} tuples..."
        )

        select_result = benchmark_select(size)
        results.append(select_result)

        print(
            f"Selection examinations: "
            f"{select_result['counter']}"
        )

        print(
            f"Wall time: "
            f"{select_result['wall_time']:.6f} seconds"
        )

        print(
            f"Output tuples: "
            f"{select_result['output_tuples']}"
        )

        print(
            f"\nRunning project with {size} tuples..."
        )

        project_result = benchmark_project(size)
        results.append(project_result)

        print(
            f"Wall time: "
            f"{project_result['wall_time']:.6f} seconds"
        )

        print(
            f"Output tuples: "
            f"{project_result['output_tuples']}"
        )

    with open(
        "performance_linear_results.csv",
        "w",
        newline="",
        encoding="utf-8"
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=[
                "operator",
                "size",
                "counter",
                "wall_time",
                "output_tuples"
            ]
        )

        writer.writeheader()
        writer.writerows(results)

    print(
        "\nResults saved to "
        "performance_linear_results.csv"
    )


if __name__ == "__main__":
    main()