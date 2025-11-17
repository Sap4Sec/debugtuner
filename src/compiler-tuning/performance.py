import json
import os
import shutil
import sys
from pathlib import Path
from time import perf_counter
from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter

sys.path.append(str(Path(__file__).resolve().parent / ".."))
from utils import log
from misc.clang_pass_names import get_pass_arg


def main(args):
    log.info(f"[debugtuner] Constructing performance scripts: INITIALIZING.")

    compiler = args.compiler if not args.cc_version else f"{args.compiler}-{args.cc_version}"
    rankings_json = args.targets / f"rankings-{compiler}.json"

    template_file = Path(__file__).resolve().parent / f"run_spec_template_{args.compiler}.sh"
    template = open(template_file).read()

    if not args.perfdir.exists():
        os.mkdir(args.perfdir)

    rankings = {}
    with open(rankings_json) as f:
        rankings = json.load(f)

    template = template.replace("PERFORMANCE_DIR_TEMPLATE", f"{args.perfdir.resolve()}")

    configurations = []
    for opt_level in rankings:
        if args.compiler == "gcc":
            ranks = list(filter(lambda x: x[0] != "inline", rankings[opt_level]))
            for name, count in [("std", 0), ("d3", 3), ("d5", 5), ("d7", 7), ("d9", 9)]:
                configs = " ".join(list(map(lambda x: f"-fno-{x[0]}", ranks[:count])))
                if name != "std":
                    configs = f" {configs}"
                configurations.append(f'["O{opt_level}-{name}"]="-O{opt_level}{configs}"')
        else:
            ranks = list(filter(lambda x: x[0] != "inlinerpass", rankings[opt_level]))
            for name, count in [("std", 0), ("d3", 3), ("d5", 5), ("d7", 7), ("d9", 9)]:
                configs = ",".join(list(map(lambda x: get_pass_arg(x[0]), ranks[:count])))
                if name != "std":
                    configs = f" -mllvm -opt-disable={configs}"
                configurations.append(f'["O{opt_level}-{name}"]="-O{opt_level}{configs}"')

    template = template.replace("CONFIGURATIONS_TEMPLATE", "\n".join(configurations))

    with open(f"{args.perfdir}/run_spec_{args.compiler}.sh", "w") as f:
        f.write(template)

    if args.compiler == "clang":

        large_dir = args.perfdir / "largs-workload"
        # construct directory
        if not large_dir.exists():
            os.mkdir(large_dir)

        template_dir = template_file = Path(__file__).resolve().parent / "large-workload"
        for file in ["autofdo_run.sh", "hyperfine_run_template.sh", "standard_run.sh", "vars.sh"]:
            shutil.copy2(template_dir / file, large_dir / file)

        template_file = Path(__file__).resolve().parent / "large-workload" / f"run_clang_template.sh"
        template = open(template_file).read()

        configurations = []
        for opt_level in rankings:
            if opt_level not in ["3"]:
                continue
            ranks = list(filter(lambda x: x[0] != "inlinerpass", rankings[opt_level]))
            for name, count in [("std", 0), ("d3", 3), ("d5", 5), ("d7", 7), ("d9", 9)]:
                configs = ",".join(list(map(lambda x: get_pass_arg(x[0]), ranks[:count])))
                if name != "std":
                    configs = f" -mllvm -opt-disable={configs}"
                configurations.append(f'"O{opt_level}-{name}:-O{opt_level}{configs}"')

        template = template.replace("CONFIGURATIONS_TEMPLATE", "\n".join(configurations))
        with open(f"{large_dir}/run_clang.sh", "w") as f:
            f.write(template)

    log.info(f"[debugtuner] Constructing performance scripts: TERMINATED.")


if __name__ == "__main__":

    parser = ArgumentParser(
        description="Generate performance evaluation scripts.",
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
        "--perfdir",
        dest="perfdir",
        type=Path,
        help="Path to output perf scripts",
        default=Path(__file__).parent.resolve() / ".." / "dt-performance",
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
