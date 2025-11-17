#!/usr/bin/env python3

import json
from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
from time import perf_counter
from pathlib import Path
from statistics import geometric_mean as mean
import sys

sys.path.append(str(Path(__file__).resolve().parent / ".."))
from utils import log
from misc.clang_pass_names import get_pass_arg


def sort_key(k):
    if k == "g":
        return (0, 0)
    return (1, int(k))


def main(args):
    log.info(f"[debutuner] Prettifying rankings: STARTING.")

    # Get compiler version and initialize debugger
    compiler = args.compiler if not args.cc_version else f"{args.compiler}-{args.cc_version}"

    rankings_json = args.targets / f"rankings-{compiler}.json"

    rankings = {}
    with open(rankings_json) as f:
        rankings = json.load(f)

    full_order = ["g", "1", "2", "3"]
    # Keep only those that actually exist
    order = [k for k in full_order if k in rankings]

    N = 10  # top rows

    # ---- Prepare columns ----
    cols = {}
    for k in order:
        col = rankings[k][:N]
        col += [("", "")] * (N - len(col))
        cols[k] = col

    # ---- Build column alignment for LaTeX ----
    # For each key: |l|r|
    align = "|c|" + "|".join("l|r" for _ in order) + "|"

    # ---- Generate LaTeX ----
    latex = []
    latex.append(r"\begin{table*}[t!]")
    latex.append(r"    \centering")
    latex.append(f"    \\caption{{Top 10 critical optimization passes in {args.compiler}.}}")
    latex.append(r"    \label{tab:top10}")
    latex.append(r"    \scriptsize")
    latex.append(f"    \\begin{{tabular}}{{{align}}}")
    latex.append(r"        \hline")

    # Header row
    header = r"        \#"
    for k in order:
        header += f" & \\multicolumn{{2}}{{c|}}{{{k}}}"
    latex.append(header + r" \\")
    latex.append(r"        \hline")

    # Rows
    for i in range(N):
        row = [str(i + 1)]
        for k in order:
            name, val = cols[k][i]
            if name:
                if args.compiler == "clang":
                    name = get_pass_arg(name, arg=False)
                row.append("{" + name + "}")
                row.append(f"{val:.2f}")
            else:
                row.append("")
                row.append("")
        latex.append("        " + " & ".join(row) + r" \\")
    latex.append(r"        \hline")
    latex.append(r"    \end{tabular}")
    latex.append(r"\end{table*}")

    print("\n".join(latex))

    log.info(f"[debutuner] Prettifying rankings: COMPLETED.")


if __name__ == "__main__":

    parser = ArgumentParser(
        description="Extract relevant source-level elements.",
        formatter_class=ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "--targets",
        dest="targets",
        type=Path,
        help="Path to targets directory",
        default=Path(__file__).parent.resolve() / ".." / "dt-targets",
    )
    parser.add_argument(
        "--compiler",
        dest="compiler",
        choices=["gcc", "clang"],
        type=str,
        help="Compiler used to build target",
        default="gcc",
    )
    parser.add_argument(
        "--cc-version",
        dest="cc_version",
        type=str,
        help="CC version to be tested",
        default="",
    )
    parser.add_argument(
        "--debug",
        dest="debug",
        action="store_true",
        help="Enable debug prints",
        default=False,
    )
    args = parser.parse_args()

    log.init(args)
    start_time = perf_counter()
    main(args)
    end_time = perf_counter()
    log.info(f"{end_time - start_time} seconds")
