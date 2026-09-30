import argparse


def write_relation(file, name, attributes, rows):
    file.write(f"{name}({','.join(attributes)}) = {{\n")

    for row in rows:
        values = []

        for value in row:
            if isinstance(value, str):
                value = value.replace("'", "''")
                values.append(f"'{value}'")
            else:
                values.append(str(value))

        file.write("(" + ",".join(values) + ")\n")

    file.write("}\n\n")


def generate_relations(n, m, match_rate):
    r_rows = []
    s_rows = []

    for i in range(n):
        r_rows.append(
            (i, i // match_rate)
        )

    for i in range(m):
        s_rows.append(
            (i // match_rate, i)
        )

    return r_rows, s_rows


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--n",
        type=int,
        required=True,
        help="Number of tuples in R"
    )

    parser.add_argument(
        "--m",
        type=int,
        required=True,
        help="Number of tuples in S"
    )

    parser.add_argument(
        "--match-rate",
        type=int,
        default=1,
        help="Number of tuples sharing each join key"
    )

    parser.add_argument(
        "--output",
        default="generated_data.ra",
        help="Output file"
    )

    args = parser.parse_args()

    if args.n <= 0 or args.m <= 0:
        raise ValueError("Tuple counts must be positive")

    if args.match_rate <= 0:
        raise ValueError("Match rate must be positive")

    r_rows, s_rows = generate_relations(
        args.n,
        args.m,
        args.match_rate
    )

    with open(
        args.output,
        "w",
        encoding="utf-8"
    ) as file:

        write_relation(
            file,
            "R",
            ["a", "b"],
            r_rows
        )

        write_relation(
            file,
            "S",
            ["b", "c"],
            s_rows
        )

    print(
        f"Generated R with {args.n} tuples "
        f"and S with {args.m} tuples."
    )

    print(
        f"Match rate: {args.match_rate}"
    )

    print(
        f"Saved to {args.output}"
    )


if __name__ == "__main__":
    main()