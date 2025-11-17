#!/usr/bin/env python3

import json
import os
import re
from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
from pathlib import Path
from time import perf_counter

import sys

sys.path.append(str(Path(__file__).resolve().parent / "llvm-ast-parser"))
import ast_parser as ap
import llvm_ast_parser as llvm_ap

sys.path.append(str(Path(__file__).resolve().parent / ".."))
from utils import log
from config import ast_config, blacklisted


def polish_traces(traces, compiler, config, pickle_dir: Path, project_dir: Path):
    """Returns a dict that contains the available variables and lines divided in categories
    also stores the uncategorized elements and computes the union
    of all the categorized and uncategorized elements.

    Args:
        traces (dict): traces dict
        compiler (str): compiler used to build target
        project_dir (str): path to project directory

    Returns:
        dict: categories dict
    """
    source_code = {}
    source_asts = {}
    traces_polished = {"vars": {}, "lines": {}}

    for opt_level in traces["traces"][compiler]:
        traces_polished["vars"][opt_level] = {}
        traces_polished["lines"][opt_level] = {}
        traces_polished["vars"][opt_level]["total"] = set()
        traces_polished["lines"][opt_level]["total"] = set()

        for disabled_opt in traces["traces"][compiler][opt_level]:
            traces_polished["vars"][opt_level][disabled_opt] = {
                "notlive": set(),
                "total": set(),
            }
            traces_polished["lines"][opt_level][disabled_opt] = {
                "total": set(),
            }

            log.info(f"[-O{opt_level}{disabled_opt}]")

            # avoid traces not computed due to same .text hash
            if traces["traces"][compiler][opt_level][disabled_opt]["variables"] == "standard":
                continue

            for source in traces["traces"][compiler][opt_level][disabled_opt]["variables"]["main"]:
                source_name = source.split("/")[-1]

                source_path = Path(source).resolve(strict=False)
                proj_root = project_dir.resolve(strict=False)
                same_source = proj_root in source_path.parents or source_path == proj_root
                if "fuzz" in source_name.lower() or not same_source:
                    continue

                if not source in traces["traces"][compiler][opt_level]["-standard"]["variables"]["main"]:
                    continue

                if source not in source_code:
                    source_filepath, n_duplicates = Path(source), 0
                    if not source_filepath.is_absolute():
                        source_filepath, n_duplicates = search_file(source, project_dir)
                    if source_filepath is None:
                        log.info(f"Source {source} not found.")
                        continue
                    if n_duplicates > 1:
                        log.info(f"File naming collision: {source}")
                        exit(1)
                    if not source_filepath.is_file():
                        log.info(f"Source {source} not found.")
                        continue
                    with open(source_filepath, "r") as file:
                        source_code[source] = file.read()

                    # BLACKLIST
                    if blacklisted(source_name, project_dir.as_posix()):
                        continue
                    # END BLACKLIST

                    log.debug(f"Source filename: {source}")
                    source_code[source] = remove_strings_and_comments(source_code[source]).splitlines()

                    ast_pickle = pickle_dir / f"{source_filepath.name}.pickle"
                    if not ast_pickle.exists():
                        source_ast = llvm_ap.parse_ast(
                            source_filepath,
                            project_dir,
                            ast_pickle,
                            config.include,
                            config.preproc,
                        )
                    else:
                        source_ast = ap.ast.AST.load(ast_pickle.as_posix())
                    source_asts[source] = source_ast

                source_ast = source_asts[source]
                for line in traces["traces"][compiler][opt_level][disabled_opt]["variables"]["main"][source]:
                    function = traces["traces"][compiler][opt_level][disabled_opt]["variables"]["main"][source][line][
                        "function"
                    ]
                    line_str = re.sub(
                        r"\/\/.*|\/\*(.|\n)*?\*\/",
                        "",
                        source_code[source][int(line) - 1].rstrip(),
                    )  # remove comments and rstrip

                    available_variables = set(
                        traces["traces"][compiler][opt_level][disabled_opt]["variables"]["main"][source][line][
                            "available"
                        ]
                    )
                    line = int(line)

                    source_function = source_ast.find_function_at(line)
                    live_vars = source_ast.find_live_vars_at(line)
                    source_live_variables = (
                        {var.name: var.is_pointer for var in live_vars} if live_vars is not None else None
                    )

                    if source_function is None:
                        log.debug(f"Line not in a function {source}:{line} (traced: {function})")
                        continue
                    else:
                        if source_function.name != function:
                            log.debug(
                                f"Wrong function in traces at line {source}:{line}: {function} != {source_function.name}"
                            )

                    for var in available_variables:
                        if var not in source_live_variables:
                            log.debug(f"var:notlive:{source}:{line}:{function}:{var}:{line_str}")
                            traces_polished["vars"][opt_level][disabled_opt]["notlive"].add(f"{source}:{line}:{var}")
                            continue
                        log.debug(f"var:{source}:{line}:{function}:{var}:{line_str}")
                        traces_polished["vars"][opt_level][disabled_opt]["total"].add(f"{source}:{line}:{var}")

                    log.debug(f"line:{source}:{line}:{line_str}")
                    traces_polished["lines"][opt_level][disabled_opt]["total"].add(f"{source}:{line}")

    # convert sets into lists
    for x in traces_polished:
        for opt_level in traces_polished[x]:
            for disabled_opt in traces_polished[x][opt_level]:
                if disabled_opt != "total":
                    traces_polished[x][opt_level]["total"] |= traces_polished[x][opt_level][disabled_opt]["total"]
                    for c in traces_polished[x][opt_level][disabled_opt]:
                        traces_polished[x][opt_level][disabled_opt][c] = sorted(
                            list(traces_polished[x][opt_level][disabled_opt][c])
                        )
            traces_polished[x][opt_level]["total"] = sorted(list(traces_polished[x][opt_level]["total"]))

    return traces_polished


def remove_strings_and_comments(source_code):
    """Return C source code without strings and comments. Substitute every multiline item with an equivalent number of blank lines.

    Args:
        source_code (str): original source code

    Returns:
        str: clean source code
    """
    pattern = r"\"(?:\\.|[^\"])*\"|\'(?:\\.|[^\'])*\'|/\*.*?\*/|//.*?$|#if 0.*?#endif"

    def replace_string_or_comment(match):
        comment_text = match.group(0)
        num_lines = comment_text.count("\n")
        return "\n" * num_lines

    return re.sub(pattern, replace_string_or_comment, source_code, flags=re.DOTALL | re.MULTILINE)


def elements_in_at_least_two_lists(*lists):
    element_count = {}

    for s in lists:
        for element in s:
            if element not in element_count:
                element_count[element] = 1
            else:
                element_count[element] += 1

    result = set()

    # Iterate through the dictionary and add elements with a count of 2 or more to the result set
    for element, count in element_count.items():
        if count >= 2:
            result.add(element)

    return result


def search_file(filename, search_path):
    search_path = Path(search_path)
    file_path = None
    count = 0
    for file in search_path.rglob(filename):
        if file.is_file():
            file_path = file
            count += 1
    return file_path, count


def main(args):
    log.info(f"[project:{args.project}, fuzz-target:{args.fuzz_target}] Polishing traces: STARTING.")

    # Get compiler version and initialize debugger
    compiler = args.compiler if not args.cc_version else f"{args.compiler}-{args.cc_version}"

    # Initialize paths and perform the initial checks
    project_dir = args.projects / args.project
    traces_json = args.targets / args.project / compiler / f"traces-{args.fuzz_target}.json"
    pickle_dir = args.targets / args.project / "pickles"

    if not pickle_dir.exists():
        os.mkdir(pickle_dir)

    traces_polished_json = args.targets / args.project / compiler / f"traces-polished-{args.fuzz_target}.json"

    if not project_dir.is_dir():
        log.info(f"[Init] Error: project directory {project_dir.as_posix()} not found.")
        exit(1)
    if not traces_json.is_file():
        log.info(f"[Init] Error: traces {traces_json.as_posix()} not found.")
        exit(1)

    # Get main traces
    with open(traces_json) as f:
        traces = json.load(f)

    # For each opt pass, check which variables are optimized
    traces_polished = polish_traces(traces, compiler, ast_config[args.project], pickle_dir, project_dir)
    with open(traces_polished_json, "w") as f:
        json.dump(traces_polished, f)

    log.info(f"[project:{args.project}, fuzz-target:{args.fuzz_target}] Polishing traces: COMPLETED.")


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
        "--projects",
        dest="projects",
        type=Path,
        help="Path to projects directory",
        default=Path(__file__).parent.resolve() / ".." / "dt-projects",
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
    parser.add_argument("--project", dest="project", type=str, help="Project name", required=True)
    parser.add_argument(
        "--fuzz-target",
        dest="fuzz_target",
        type=str,
        help="Fuzz target name",
        required=True,
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
