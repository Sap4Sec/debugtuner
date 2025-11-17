#!/usr/bin/env python3

import json
import hashlib
import re
from pathlib import Path
from time import perf_counter
from elftools.elf.elffile import ELFFile
from multiprocessing import Pool
from subprocess import *
from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
import sys

sys.path.append(str(Path(__file__).resolve().parent / ".."))
from utils import log, tracer


def get_inputs(input_dir):
    """Return the set of input filepaths.

    Args:
        input_dir (Path): input directory

    Returns:
        set: input filepaths
    """
    inputs = set()

    if not input_dir.is_dir():
        log.info(f"Error: input directory {input_dir} not found.")
        exit(1)
    for input_filepath in input_dir.iterdir():
        if input_filepath.is_file():
            inputs.add(input_filepath)

    return inputs


def get_text_section_hash(binary):
    """Compute the hash of the .text section

    Args:
        binary (Path): Path to binary

    Returns:
        str: .text section hash
    """
    with open(binary, "rb") as f:
        elf = ELFFile(f)

        text_section = elf.get_section_by_name(".text")
        if text_section:
            return hashlib.sha256(text_section.data()).hexdigest()
        else:
            log.info("Error: .text section not found")
            exit(1)


def sort_by_priority(path):
    """O0-all, then standard, then alphabetically"""

    basename = path.name

    # First, "-O0-all"
    if "-O0-all" in basename:
        return (0, basename)

    # Next, "-O\d-standard"
    regex_pattern = r"-O(0|1|2|3|g|s|z)-standard$"
    match = re.search(regex_pattern, basename)
    if match:
        return (1, basename)

    # Finally, sort alphabetically
    return (2, basename)


def merge_functions(traces):
    """Return the functions removing inconsistencies.

    Args:
        traces (dict): traces dict

    Returns:
        dict: key = func, value = variables types
    """
    log.info(f"Functions merging: STARTED")
    output = {}
    for opt_level in traces:
        for disabled_opt in traces[opt_level]:
            if "functions" in traces[opt_level][disabled_opt]:
                for i, data in traces[opt_level][disabled_opt]["functions"].items():
                    for f, types in data.items():
                        if f not in output:
                            output[f] = types
                        elif types != output[f]:
                            log.info(
                                f"[-O{opt_level} {disabled_opt}] Types inconsistency: {i}:{f} - {output[f]} - {types}"
                            )
                            for var, t in types.items():
                                if var not in output[f]:
                                    output[f][var] = t

    output = {key: output[key] for key in sorted(output.keys())}
    log.info(f"Functions merging: COMPLETED")
    return output


def compute_single_trace(binary_filepath, opt_level, disabled_opt, compiler, inputs):
    # Initialize debugger
    dbg = ["gdb", "lldb"]["clang" in compiler]

    log.info(f"[-O{opt_level} {disabled_opt}] Debug traces computation: STARTING")

    input_paths = " ".join(map(lambda x: str(x), inputs))
    variables, functions = tracer.get_variables(binary_filepath, input_paths, dbg)

    log.info(f"[-O{opt_level} {disabled_opt}] Debug traces computation: COMPLETED")

    return variables, functions


def compute_traces(target_info, target_dir, compiler, inputs, target, proc):
    """Compute traces and remove inconsistencies. Traces are stored in target_info.

    Args:
        target_info (dict): dictionary that will contain the traces
        target_dir (str): path to target directory
        compiler (str): compiler used to build target
        inputs (set): input filepaths
        target (str): target binary filename
    """

    traces = {}

    # Iterate over target_dir to load one binary per time
    pool = Pool(processes=proc)

    for binary_dir in sorted(target_dir.iterdir(), key=sort_by_priority):

        if binary_dir.is_dir() and "-O" in binary_dir.name:
            opt_level = binary_dir.name.split("-O")[1][0]
            disabled_opt = binary_dir.name.split("-O")[1][1:]
        else:
            continue

        # Check if binary exists
        binary_filepath = binary_dir / target
        if not binary_filepath.is_file():
            log.info(f"Error: binary {binary_filepath} not found.")
            continue

        if opt_level not in target_info["traces"][compiler]:
            target_info["traces"][compiler][opt_level] = {}
        if disabled_opt not in target_info["traces"][compiler][opt_level]:
            target_info["traces"][compiler][opt_level][disabled_opt] = {}
            target_info["traces"][compiler][opt_level][disabled_opt]["variables"] = {}
            target_info["traces"][compiler][opt_level][disabled_opt]["functions"] = {}

        # Compute .text hash and skip debug traces if equal to standard .text
        text_section_hash = get_text_section_hash(binary_filepath)
        target_info["traces"][compiler][opt_level][disabled_opt][".text_hash"] = text_section_hash
        if (
            "-O0-all" not in binary_dir.name
            and not re.search(r"-O(0|1|2|3|g|s|z)-standard$", binary_dir.name)
            and text_section_hash == target_info["traces"][compiler][opt_level]["-standard"][".text_hash"]
        ):
            log.info(f"[-O{opt_level}{disabled_opt}] skipped: standard .text")
            target_info["traces"][compiler][opt_level][disabled_opt]["variables"] = "standard"
            continue

        # Check if main debug trace for current binary has already been computed
        if "main" in target_info["traces"][compiler][opt_level][disabled_opt]["variables"]:
            log.info(f"[-O{opt_level}{disabled_opt}] Main trace already computed")
            continue

        # All -all and -standard binaries must be computed separately so that hashes are ready when needed
        # TODO: this can also be done in parallel ideally, maybe in another pool? Or busy waiting
        if "-all" in binary_dir.name or "-standard" in binary_dir.name:
            (
                target_info["traces"][compiler][opt_level][disabled_opt]["variables"]["main"],
                target_info["traces"][compiler][opt_level][disabled_opt]["functions"]["main"],
            ) = compute_single_trace(binary_filepath, opt_level, disabled_opt, compiler, inputs)
        # All the binaries with disabled opt can be computed in parallel
        else:
            if proc > 1:
                traces[(opt_level, disabled_opt)] = pool.apply_async(
                    func=compute_single_trace,
                    args=(binary_filepath, opt_level, disabled_opt, compiler, inputs),
                )
            else:
                (
                    target_info["traces"][compiler][opt_level][disabled_opt]["variables"]["main"],
                    target_info["traces"][compiler][opt_level][disabled_opt]["functions"]["main"],
                ) = compute_single_trace(binary_filepath, opt_level, disabled_opt, compiler, inputs)

    pool.close()
    pool.join()

    if proc > 1:
        for (opt_level, disabled_opt), trace in traces.items():
            (
                target_info["traces"][compiler][opt_level][disabled_opt]["variables"]["main"],
                target_info["traces"][compiler][opt_level][disabled_opt]["functions"]["main"],
            ) = trace.get()

    # Merge functions
    if not "merged" in target_info["functions"]:
        target_info["functions"]["merged"] = merge_functions(target_info["traces"][compiler])
    for opt_level in list(target_info["traces"][compiler]):
        for disabled_opt in list(target_info["traces"][compiler][opt_level]):
            if "functions" in target_info["traces"][compiler][opt_level][disabled_opt]:
                del target_info["traces"][compiler][opt_level][disabled_opt]["functions"]


def main(args):
    log.info(f"[project:{args.project}, fuzz-target:{args.fuzz_target}] Debug traces: INITIALIZING.")

    # Get compiler version
    compiler = args.compiler if not args.cc_version else f"{args.compiler}-{args.cc_version}"

    # Check if targets/project/compiler/ exists
    target_dir = args.targets / args.project / compiler
    if not target_dir.is_dir():
        log.info(f"Error: target directory {target_dir.as_posix()} not found.")
        exit(1)

    # Load target json (if exists)
    target_json = target_dir / f"traces-{args.fuzz_target}.json"
    if target_json.is_file():
        log.info(f"Found {target_json}. Reading traces...")
        with open(target_json, "r") as f:
            target_info = json.load(f)
    else:
        target_info = {}
        target_info["inputs"] = 0
        target_info["traces"] = {}
        target_info["functions"] = {}

    # Initialize compiler entry in traces dict
    if compiler not in target_info["traces"]:
        target_info["traces"][compiler] = {}

    # Get inputs from corpus/project/fuzz-target directory
    inputs = get_inputs(args.corpus / args.project / args.fuzz_target)
    log.info(f"Found {len(inputs)} inputs to be injected.")
    if len(inputs) == 0:
        exit(1)
    target_info["inputs"] = len(inputs)

    # Compute traces (removing inconsistencies)
    compute_traces(target_info, target_dir, compiler, inputs, args.fuzz_target, args.proc)

    # Write traces in json
    with open(target_json, "w") as f:
        json.dump(target_info, f)

    log.info(f"[project:{args.project}, fuzz-target:{args.fuzz_target}] Debug traces: TERMINATED.")


if __name__ == "__main__":

    parser = ArgumentParser(
        description="Compute debug traces of a fuzz-target.",
        formatter_class=ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "--targets",
        dest="targets",
        type=Path,
        help="Path to targets directory",
        default=Path(__file__).parent.resolve() / ".." / "dt-targets",
    )
    parser.add_argument("--proc", dest="proc", type=int, help="Number of processes to use", default=1)
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
        "--project",
        dest="project",
        type=str,
        help="Project to be analyzed",
        required=True,
    )
    parser.add_argument(
        "--corpus",
        dest="corpus",
        type=Path,
        help="Path to the corpus directory",
        default=Path(__file__).parent.resolve() / ".." / "dt-corpus-min",
    )
    parser.add_argument("--fuzz-target", dest="fuzz_target", type=str, help="Fuzz target", required=True)
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
