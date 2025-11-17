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
    log.info(f"[debutuner] Get flags for custom configurations: STARTING.")

    # Get compiler version and initialize debugger
    compiler = args.compiler if not args.cc_version else f"{args.compiler}-{args.cc_version}"

    rankings_json = args.targets / f"rankings-{compiler}.json"

    rankings = {}
    with open(rankings_json) as f:
        rankings = json.load(f)

    configurations = []
    for opt_level in rankings:
        if args.compiler == "gcc":
            ranks = list(filter(lambda x: x[0] != "inline", rankings[opt_level]))
            for _, count in [("d3", 3), ("d5", 5), ("d7", 7), ("d9", 9)]:
                configs = " ".join(list(map(lambda x: f"-fno-{x[0]}", ranks[:count])))
                configurations.append(f"{opt_level}{configs}")
        else:
            ranks = list(filter(lambda x: x[0] != "inlinerpass", rankings[opt_level]))
            for _, count in [("d3", 3), ("d5", 5), ("d7", 7), ("d9", 9)]:
                configs = ",".join(list(map(lambda x: get_pass_arg(x[0]), ranks[:count])))
                configurations.append(f"{opt_level}{configs}")

    print(
        f"python3 debugtuner.py --compiler {args.compiler} --stages build traces static metrics --opts \"{':'.join(configurations)}\" --custom --proc N"
        + ("--minimal" if args.minimal else "")
    )

    log.info(f"[debutuner] Get flags for custom configurations: COMPLETED.")


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
        "--minimal",
        dest="minimal",
        action="store_true",
        help="Enable minimal workload (libpng, zydis)",
        default=False,
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
