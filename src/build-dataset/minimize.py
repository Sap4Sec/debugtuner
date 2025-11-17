#!/usr/bin/env python3

import subprocess
import json
import shutil
from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
from pathlib import Path
from multiprocessing import Pool
from time import perf_counter
import sys

sys.path.append(str(Path(__file__).resolve().parent / ".."))
from utils import log, tracer


def minimize_cmin(corpus_in, corpus_cmin, binary):
    """Run afl-cmin on input corpus.

    Args:
        corpus_in (str): path to input corpus
        corpus_cmin (str): path to corpus-cmin
        binary (str): path to instrumented binary
    """
    cmin_cmd = [
        "afl-cmin",
        "-e",
        "-i",
        corpus_in,
        "-o",
        corpus_cmin,
        "--",
        binary,
        "@@",
    ]
    log.info(" ".join(cmin_cmd))
    result = subprocess.run(cmin_cmd, capture_output=True)
    for l in result.stdout.decode().split("\n"):
        if l.startswith(("[*]", "[+]", "[-]")):
            log.debug(l)
    if result.returncode != 0:
        log.info(f"Error: afl-cmin exit code = {result.returncode}")
        exit(1)


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


def compute_traces(binary_O0, inputs, dbg, proc):
    """Compute and return traces at O0-all for each input

    Args:
        binary_O0 (Path): path to binary compiled without opts
        inputs (set): input paths set
        dbg (str): debugger
        proc (int): number of processes

    Returns:
        dict: traces
    """
    traces = {}
    results = {}
    pool = Pool(processes=proc)
    for input_filepath in inputs:

        input_filename = input_filepath.name
        traces[input_filename] = {}
        if proc > 1:
            results[input_filename] = pool.apply_async(func=tracer.get_variables, args=(binary_O0, input_filepath, dbg))
        else:
            traces[input_filename]["variables"], traces[input_filename]["functions"] = tracer.get_variables(
                binary_O0, input_filepath, dbg
            )

    pool.close()
    pool.join()

    # Add traces to traces dict if proc > 1
    if proc > 1:
        for input_filename, trace in results.items():
            traces[input_filename]["variables"], traces[input_filename]["functions"] = trace.get()

    return traces


def minimize_traces(traces):
    """Minimize inputs based on new lines that are stepped and check that
    on the same line there is the same var status.
    Return the set of min inputs

    Args:
        traces (dict): debug traces

    Returns:
        set: min inputs filenames
    """
    main_trace = {}
    inputs_min = set()

    # order for decrescent number of lines traces, to minimize number of input files
    ordered = []
    for i, trace in traces.items():
        val = 0
        for source, lines in trace["variables"].items():
            val += len(lines)
        ordered.append((i, val))
    ordered_inputs = list(map(lambda x: x[0], sorted(ordered, key=lambda x: x[1])))

    for i in ordered_inputs:
        trace = traces[i]

        for source, lines in trace["variables"].items():
            if source not in main_trace:
                main_trace[source] = {}
            for line, status in lines.items():
                if line not in main_trace[source]:
                    # if the current input allow to step on a new line it has to be added to the minimum set
                    inputs_min.add(i)
                    main_trace[source][line] = status
                elif status != main_trace[source][line]:
                    # on the same line the status has to be the same
                    log.info(
                        f"[{i}] Consistency check failed {source}:{line} - main trace: {main_trace[source][line]} - current trace: {status}"
                    )

    return inputs_min


def main(args):
    log.info(f"[project:{args.project}, fuzz-target:{args.fuzz_target}] Input minimization: STARTING.")

    # Get compiler version and initialize debugger
    compiler = args.compiler if not args.cc_version else f"{args.compiler}{args.cc_version}"
    dbg = ["gdb", "lldb"]["clang" in compiler]

    # Initialize paths and perform the initial checks
    corpus_in = args.corpus / args.project / args.fuzz_target
    corpus_cmin = args.corpus_cmin / args.project / args.fuzz_target
    corpus_min = args.corpus_min / args.project / args.fuzz_target
    binary_cmin = args.targets / args.project / args.afl_compiler / f"{args.project}-O0-standard" / args.fuzz_target
    binary_O0 = args.targets / args.project / compiler / f"{args.project}-O0-standard" / args.fuzz_target

    if corpus_min.is_dir() and any(corpus_min.iterdir()):
        log.info(f"[Init] Found not empty output corpus directory {corpus_min.as_posix()}. Exiting...")
        exit(0)

    skip_stage_0 = False
    if not corpus_in.is_dir():
        log.info(f"[Init] Error: input corpus directory {corpus_in.as_posix()} not found.")
        exit(1)
    if not binary_cmin.is_file():
        log.info(f"[Init] Error: binary instrumented for afl-cmin {binary_cmin.as_posix()} not found.")
        skip_stage_0 = True
    if not binary_O0.is_file():
        log.info(f"[Init] Error: binary at O0-all {binary_O0.as_posix()} not found.")
        exit(1)

    # Stage 0 - cmin
    if not skip_stage_0:
        if corpus_cmin.exists():
            log.info(f"[Stage 0] Found corpus cmin directory {corpus_cmin.as_posix()}. Skipping afl-cmin minimization.")
        else:
            log.info(f"[Stage 0] afl-cmin minimization: STARTING.")
            rm_regressions_cmd = ["rm", "-rf", (corpus_in / "regressions").as_posix()]
            log.info(" ".join(rm_regressions_cmd))
            subprocess.run(rm_regressions_cmd)
            minimize_cmin(corpus_in.as_posix(), corpus_cmin.as_posix(), binary_cmin.as_posix())
            log.info(f"[Stage 0] afl-cmin minimization: COMPLETED.")
    else:
        shutil.copytree(corpus_in.as_posix(), corpus_cmin.as_posix())

    # Get inputs filepaths for stage 1
    inputs_stage1 = get_inputs(corpus_cmin)
    log.info(f"[Stage 0] Input set len reduced from {len(get_inputs(corpus_in))} to {len(inputs_stage1)}.")
    if len(inputs_stage1) == 0:
        exit(1)

    # Stage 1 - minimization with traces
    # if traces with at O0-all have already been computed: compute directly the min set
    # else: compute the traces and then use them to compute the min set
    traces_O0_json = args.targets / args.project / compiler / f"minimize-{args.fuzz_target}.json"
    if traces_O0_json.is_file():
        with open(traces_O0_json) as f:
            traces = json.load(f)
        if len(traces) == len(inputs_stage1):
            log.info(f"[Stage 1] Found O0 traces in {traces_O0_json}. Skipping traces computation.")
        else:
            log.info(f"[Stage 1] Error: Found O0 traces in {traces_O0_json} but with a different inputs set.")
            exit(1)
    else:
        log.info(f"[Stage 1] O0 traces computation: STARTING.")
        traces = compute_traces(binary_O0, inputs_stage1, dbg, args.proc)
        log.info(f"[Stage 1] O0 traces computation: COMPLETED.")

        # Write traces in json
        with open(traces_O0_json, "w") as f:
            json.dump(traces, f)

    # Extract minimum inputs set
    inputs_stage2 = minimize_traces(traces)
    log.info(f"[Stage 1] Input set len reduced from {len(inputs_stage1)} to {len(inputs_stage2)}.")
    inputs_min = inputs_stage2

    # Copy min input set in corpus-min dir
    corpus_min.mkdir(parents=True, exist_ok=True)
    log.info(f"{corpus_min} directory created.")
    for input_filename in inputs_min:
        src_path = corpus_in / input_filename
        dest_path = corpus_min / input_filename
        shutil.copy(src_path, dest_path)
        log.debug(f"cp {src_path} {dest_path}")

    log.info(f"[project:{args.project}, fuzz-target:{args.fuzz_target}] Input minimization: COMPLETED.")


if __name__ == "__main__":

    parser = ArgumentParser(
        description="Minimize corpora in 3 stages: afl-cmin -> traces -> k-means.",
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
        "--afl-compiler",
        dest="afl_compiler",
        choices=["afl-clang-fast"],
        type=str,
        help="AFL++ compiler used to build target",
        default="afl-clang-fast",
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
        "--corpus",
        dest="corpus",
        type=Path,
        help="Path to the corpus directory",
        default=Path(__file__).parent.resolve() / ".." / "dt-projects" / "oss-fuzz" / "build" / "corpus",
    )
    parser.add_argument(
        "--corpus-cmin",
        dest="corpus_cmin",
        type=Path,
        help="Path to the cmin corpus directory",
        default=Path(__file__).parent.resolve() / ".." / "dt-corpus-cmin",
    )
    parser.add_argument(
        "--corpus-min",
        dest="corpus_min",
        type=Path,
        help="Path to the output minimized corpus directory",
        default=Path(__file__).parent.resolve() / ".." / "dt-corpus-min",
    )
    parser.add_argument("--proc", dest="proc", type=int, help="Number of processes to use", default=1)
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
