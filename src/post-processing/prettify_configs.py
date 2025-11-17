#!/usr/bin/env python3

import json
from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
from time import perf_counter
from pathlib import Path
from statistics import geometric_mean as mean
import sys

sys.path.append(str(Path(__file__).resolve().parent / ".."))
from utils import log
import config
from misc.clang_pass_names import get_pass_arg


def sort_key(k):
    if k == "g":
        return (0, 0)
    return (1, int(k))


def main(args):
    log.info(f"[debutuner] Prettifying configurations results: STARTING.")

    compiler = args.compiler if not args.cc_version else f"{args.compiler}-{args.cc_version}"

    configs_res_avail = {}
    configs_res_linec = {}
    for project in config.projects[args.compiler]:
        metrics_json = args.targets / project / compiler / "metrics.json"
        metrics = {}

        if not metrics_json.exists():
            continue

        if project not in configs_res_avail:
            configs_res_avail[project] = {}
            configs_res_linec[project] = {}

        with open(metrics_json) as f:
            metrics = json.load(f)

        for conf in metrics["availability-variables"]:
            delim = "-fno-" if args.compiler == "gcc" else "-no-"
            opts = conf.split(delim)
            opt_level = conf.split("-")[0]
            if len(opts[1:]) in [3, 5, 7, 9]:
                configs_res_avail[project][f"O{opt_level}-d{len(opts[1:])}"] = metrics["availability-variables"][conf]
            elif "standard" in conf:
                configs_res_avail[project][f"O{opt_level}-std"] = metrics["availability-variables"][conf]

        for conf in metrics["line-coverage"]:
            delim = "-fno-" if args.compiler == "gcc" else "-no-"
            opts = conf.split(delim)
            opt_level = conf.split("-")[0]
            if len(opts[1:]) in [3, 5, 7, 9]:
                configs_res_linec[project][f"O{opt_level}-d{len(opts[1:])}"] = metrics["line-coverage"][conf]
            elif "standard" in conf:
                configs_res_linec[project][f"O{opt_level}-std"] = metrics["line-coverage"][conf]

    products = {}
    for prog in configs_res_avail:
        products[prog] = {}
        for cfg in configs_res_avail[prog]:
            products[prog][cfg] = configs_res_avail[prog][cfg] * configs_res_linec[prog][cfg]

    # Desired order
    group_order = ["Og", "O1", "O2", "O3"]
    suffix_order = ["std", "d3", "d5", "d7", "d9"]

    # Generate keys in correct order
    keys = []
    for g in group_order:
        for s in suffix_order:
            k = f"{g}-{s}"
            if k in products["wasm3"]:
                keys.append(k)

    # Geometric-mean average for each column
    avg = {k: mean([products[p][k] for p in products]) for k in keys}

    # Print LaTeX table
    print(r"\begin{table}[h!]")
    print(r"\centering")
    print(r"\begin{tabular}{l" + "c" * len(keys) + "}")
    print(r"\toprule")
    print(" & " + " & ".join(keys) + r" \\")
    print(r"\midrule")

    # Rows for programs
    for impl, results in products.items():
        row = [f"{results[k]:.4f}" for k in keys]
        print(impl + " & " + " & ".join(row) + r" \\")

    print(r"\midrule")

    # Geometric mean row
    avg_row = [f"{avg[k]:.4f}" for k in keys]
    print("avg & " + " & ".join(avg_row) + r" \\")

    print(r"\bottomrule")
    print(r"\end{tabular}")
    print(r"\end{table}")


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
