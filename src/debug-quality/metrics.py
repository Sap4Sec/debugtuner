#!/usr/bin/env python3

import json
from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
from time import perf_counter
from pathlib import Path
from statistics import geometric_mean as mean
import sys

sys.path.append(str(Path(__file__).resolve().parent / ".."))
from utils import log
from config import projects


def compute_availability(project_dir, project, compiler, project_stats):
    global computed_lines_next
    computed_lines_next = {}

    key = "availability-variables"
    project_stats[key] = {}

    project_available_standard = {}
    project_available_singles = {}

    project_lines_standard = {}
    project_lines_singles = {}

    for fuzz_target in projects[compiler.split("-")[0]][project]:
        log.info(f"Computing availability of variables for target {project}-{fuzz_target}")
        filepath = project_dir / f"traces-polished-{fuzz_target}.json"
        if not filepath.is_file():
            continue

        categorized_total = json.load(open(filepath))
        categorized = categorized_total["vars"]
        categorized_lines = categorized_total["lines"]

        for opt_level in categorized:
            if opt_level not in project_available_standard:
                project_available_standard[opt_level] = set()
                project_available_singles[opt_level] = {}
                project_lines_standard[opt_level] = set()
                project_lines_singles[opt_level] = {}

            if opt_level not in computed_lines_next:
                computed_lines_next[opt_level] = {}

            if "-standard" not in computed_lines_next[opt_level]:
                computed_lines_next[opt_level]["-standard"] = set()

            project_lines_standard[opt_level] |= set(categorized_lines[opt_level]["-standard"]["total"])

            project_available_standard[opt_level] |= set(categorized[opt_level]["-standard"]["total"])

            if opt_level == "0":
                continue

            for disabled_opt in categorized[opt_level]:
                if disabled_opt in ["-standard", "total"]:
                    continue
                if disabled_opt not in project_available_singles[opt_level]:
                    project_available_singles[opt_level][disabled_opt] = set()
                    project_lines_singles[opt_level][disabled_opt] = set()

                if disabled_opt not in computed_lines_next[opt_level]:
                    computed_lines_next[opt_level][disabled_opt] = set()

                project_lines_singles[opt_level][disabled_opt] |= set(
                    categorized_lines[opt_level][disabled_opt]["total"]
                )

                project_available_singles[opt_level][disabled_opt] |= set(categorized[opt_level][disabled_opt]["total"])

    vars_per_line = {}
    vars_per_line_singles = {}
    for opt_level in project_available_standard:
        vars_per_line[opt_level] = {}
        vars_per_line_singles[opt_level] = {}

        project_available_standard["0"] = set(
            filter(
                lambda x: not "fuzz" in x.lower(),
                project_available_standard["0"],
            )
        )
        project_available_standard[opt_level] &= project_available_standard["0"]

        vars_per_line_list = list(
            map(
                lambda x: (":".join(x.split(":")[:2]), x.split(":")[-1]),
                project_available_standard[opt_level],
            )
        )
        for a, b in vars_per_line_list:
            if a not in vars_per_line[opt_level]:
                vars_per_line[opt_level][a] = set()
            vars_per_line[opt_level][a].add(b)

        for line in project_lines_standard[opt_level]:
            if line not in vars_per_line[opt_level]:
                vars_per_line[opt_level][line] = set()

        for disabled_opt in project_available_singles[opt_level]:
            vars_per_line_singles[opt_level][disabled_opt] = {}

            project_available_singles[opt_level][disabled_opt] &= project_available_standard["0"]

            vars_per_line_list = list(
                map(
                    lambda x: (":".join(x.split(":")[:2]), x.split(":")[-1]),
                    project_available_singles[opt_level][disabled_opt],
                )
            )
            for a, b in vars_per_line_list:
                if a not in vars_per_line_singles[opt_level][disabled_opt]:
                    vars_per_line_singles[opt_level][disabled_opt][a] = set()
                vars_per_line_singles[opt_level][disabled_opt][a].add(b)

            for line in project_lines_singles[opt_level]:
                if line not in vars_per_line_singles[opt_level][disabled_opt]:
                    vars_per_line_singles[opt_level][disabled_opt][line] = set()

    availability_data_standard = {}
    availability_data_singles = {}
    for opt_level in vars_per_line:
        availability_data_standard[opt_level] = []
        availability_data_singles[opt_level] = {}

        for line in vars_per_line[opt_level]:
            if line not in vars_per_line["0"]:
                continue

            if len(vars_per_line["0"][line]) == 0:
                continue

            if line in computed_lines_next[opt_level]["-standard"]:
                continue
            computed_lines_next[opt_level]["-standard"].add(line)

            availability_data_standard[opt_level].append(
                (len(vars_per_line[opt_level][line] & vars_per_line["0"][line]) / len(vars_per_line["0"][line])) + 1
            )

        for disabled_opt in vars_per_line_singles[opt_level]:
            availability_data_singles[opt_level][disabled_opt] = []

            if disabled_opt not in computed_lines_next[opt_level]:
                computed_lines_next[opt_level][disabled_opt] = set()

            for line in vars_per_line_singles[opt_level][disabled_opt]:
                if line not in vars_per_line["0"]:
                    continue

                if len(vars_per_line["0"][line]) == 0:
                    continue

                if line in computed_lines_next[opt_level][disabled_opt]:
                    continue
                computed_lines_next[opt_level][disabled_opt].add(line)

                availability_data_singles[opt_level][disabled_opt].append(
                    (
                        len(vars_per_line_singles[opt_level][disabled_opt][line] & vars_per_line["0"][line])
                        / len(vars_per_line["0"][line])
                    )
                    + 1
                )

    for opt_level in availability_data_standard:
        if opt_level == "0":
            continue

        project_stats[key][f"{opt_level}-standard"] = mean(availability_data_standard[opt_level]) - 1

        for disabled_opt in availability_data_singles[opt_level]:
            if len(availability_data_singles[opt_level][disabled_opt]) == 0:
                project_stats[key][f"{opt_level}{disabled_opt}"] = 0
                continue
            project_stats[key][f"{opt_level}{disabled_opt}"] = (
                mean(availability_data_singles[opt_level][disabled_opt]) - 1
            )


def compute_line_coverage(project_dir, project, compiler, project_stats):
    key = "line-coverage"
    project_stats[key] = {}

    project_lines_standard = {}
    project_lines_singles = {}

    for fuzz_target in projects[compiler.split("-")[0]][project]:
        log.info(f"Computing line coverage for target {project}-{fuzz_target}")
        filepath = project_dir / f"traces-polished-{fuzz_target}.json"
        if not filepath.is_file():
            continue

        categorized_total = json.load(open(filepath))
        categorized = categorized_total["lines"]

        for opt_level in categorized:
            if opt_level not in project_lines_standard:
                project_lines_standard[opt_level] = set()
                project_lines_singles[opt_level] = {}

            project_lines_standard[opt_level] |= set(categorized[opt_level]["-standard"]["total"])

            if opt_level == "0":
                continue

            for disabled_opt in categorized[opt_level]:
                if disabled_opt in ["-standard", "total"]:
                    continue
                if disabled_opt not in project_lines_singles[opt_level]:
                    project_lines_singles[opt_level][disabled_opt] = set()

                project_lines_singles[opt_level][disabled_opt] |= set(categorized[opt_level][disabled_opt]["total"])

    for opt_level in project_lines_standard:
        if opt_level == "0":
            continue

        project_lines_standard[opt_level] &= project_lines_standard["0"]
        value = len(project_lines_standard[opt_level]) / len(project_lines_standard["0"])
        project_stats[key][f"{opt_level}-standard"] = value

        for disabled_opt in project_lines_singles[opt_level]:
            project_lines_singles[opt_level][disabled_opt] &= project_lines_standard["0"]
            value = len(project_lines_singles[opt_level][disabled_opt]) / len(project_lines_standard["0"])
            project_stats[key][f"{opt_level}{disabled_opt}"] = value


def main(args):
    log.info(f"[project:{args.project}] Debuggability computation: STARTING.")

    compiler = args.compiler if not args.cc_version else f"{args.compiler}-{args.cc_version}"
    project_dir = args.targets / args.project / compiler
    metrics_file = args.targets / args.project / compiler / "metrics.json"

    if not project_dir.is_dir():
        log.info(f"[Init] Error: project directory {project_dir.as_posix()} not found.")
        exit(1)

    if args.project not in projects[args.compiler]:
        log.info(f"[Init] Error: project{args.project} not found.")
        exit(1)

    project_stats = {}
    compute_availability(project_dir, args.project, compiler, project_stats)
    compute_line_coverage(project_dir, args.project, compiler, project_stats)

    with open(metrics_file, "w") as f:
        json.dump(project_stats, f)

    log.info(f"[project:{args.project}] Debuggability computation: COMPLETED.")


if __name__ == "__main__":

    parser = ArgumentParser(
        description="Compute differences between optimization levels.",
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
        "--projects",
        dest="projects",
        type=Path,
        help="Path to projects directory",
        default=Path(__file__).parent.resolve() / ".." / "dt-projects",
    )
    parser.add_argument("--project", dest="project", type=str, help="Project")
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
