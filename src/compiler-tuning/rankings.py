import json
from statistics import mean, geometric_mean
import sys
from pathlib import Path
from time import perf_counter
from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter

sys.path.append(str(Path(__file__).resolve().parent / ".."))
import config
from utils import log


def main(args):
    log.info(f"[debugtuner] Constructing Rankings: INITIALIZING.")

    keys = ("availability-variables", "line-coverage")
    compiler = args.compiler if not args.cc_version else f"{args.compiler}-{args.cc_version}"

    overall_stats = {}

    projects = config.projects[args.compiler]
    if args.minimal:
        projects = config.projects_minimal[args.compiler]

    for project_name in projects:

        metrics_file = f"{args.targets}/{project_name}/{compiler}/metrics.json"
        metrics = json.load(open(metrics_file))

        stats = {}

        for opt_pass, val in metrics[keys[0]].items():
            opt_level = opt_pass.split("-")[0]
            if opt_level not in stats:
                stats[opt_level] = []

            if opt_pass not in metrics[keys[1]]:
                continue

            avail = metrics[keys[0]][opt_pass]
            lines = metrics[keys[1]][opt_pass]
            val = avail * lines
            opt_pass = opt_pass[2:].replace("fno-", "").replace("no-", "").replace("opt-disable=", "")

            stats[opt_level].append((opt_pass, val))

        for opt_level in stats:
            if opt_level not in overall_stats:
                overall_stats[opt_level] = {}

            sorted_stats = sorted(stats[opt_level], key=lambda x: x[1], reverse=True)

            sorted_filtered_stats = []
            for stat in sorted_stats:
                if "standard" in stat[0]:
                    sorted_filtered_stats.insert(0, stat)
                    continue
                sorted_filtered_stats.append(stat)

            num_neg = sum([1 for _, value in sorted_filtered_stats if value < sorted_filtered_stats[0][1]])
            for i, (opt_pass, value) in enumerate(sorted_filtered_stats):
                if i == 0:
                    continue

                if opt_pass not in overall_stats[opt_level]:
                    overall_stats[opt_level][opt_pass] = []

                value = value / sorted_filtered_stats[0][1]
                if value == 0:
                    value = 1
                    i = len(sorted_filtered_stats) - num_neg - 1
                overall_stats[opt_level][opt_pass].append((i, value + 1, project_name))

    final_stats = {}
    for opt_level in overall_stats:
        if opt_level not in final_stats:
            final_stats[opt_level] = []
        for opt_pass in overall_stats[opt_level]:

            n_proj = len(overall_stats[opt_level][opt_pass])
            if n_proj != len(projects):
                continue

            avg_pos = mean(map(lambda x: x[0], overall_stats[opt_level][opt_pass]))
            avg_val = geometric_mean(map(lambda x: x[1], overall_stats[opt_level][opt_pass])) - 1

            final_stats[opt_level].append((opt_pass, avg_pos, avg_val))

        final_stats[opt_level] = sorted(final_stats[opt_level], key=lambda x: x[1])

    rankings_json = args.targets / f"rankings-{compiler}.json"
    rankings = {}

    for opt_level in final_stats:
        rankings[opt_level] = []
        for i, elem in enumerate(final_stats[opt_level]):
            if i > 9:
                break
            rankings[opt_level].append([elem[0], (elem[2] - 1) * 100])

    with open(rankings_json, "w") as f:
        json.dump(rankings, f)

    log.info(f"[debugtuner] Constructing Rankings: TERMINATED.")


if __name__ == "__main__":

    parser = ArgumentParser(
        description="Construct optimization pass rankings",
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
