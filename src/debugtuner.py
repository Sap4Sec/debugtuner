#!/usr/bin/env python3

import subprocess
from time import perf_counter
from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
from pathlib import Path
from datetime import datetime
import os

import config
from utils import log


def run_cmd(cmd, log_file, env=None):
    log.info(" ".join(cmd))

    log_file = Path(str(log_file).replace(".log", f"-{datetime.now().strftime('%Y%m%d-%H%M%S')}.log"))

    run_env = os.environ.copy()
    if env is not None:
        for key in env:
            run_env[key] = env[key]

    start = perf_counter()
    with open(log_file, "w") as f:
        result = subprocess.run(cmd, stderr=subprocess.STDOUT, stdout=f, env=run_env)
    end = perf_counter()
    log.info(f"{end - start} seconds")
    result.check_returncode()

    # Remove seed and date from logs
    subprocess.run(["sed", "-i", "s/\[[^]]*\] //", log_file])


def main(args):
    base = Path(__file__).parent.resolve()

    # Create log directory
    args.log.mkdir(parents=True, exist_ok=True)

    # Get compiler version
    compiler = args.compiler if not args.cc_version else f"{args.compiler}-{args.cc_version}"
    cpp_compiler = args.cpp_compiler if not args.cc_version else f"{args.cpp_compiler}-{args.cc_version}"

    projects = config.projects[args.compiler]
    if args.minimal:
        projects = config.projects_minimal[args.compiler]

    full_opts = args.opts
    if compiler == "clang" and "g" in full_opts:
        full_opts = full_opts.replace(":g", "")

    # 0. Build targets
    if args.all_stages or "build" in args.stages:
        for p, targets in projects.items():

            log.debug(f"Building {p} with {compiler}...")
            build_cmd = [
                (base / "build-dataset" / "build.sh").as_posix(),
                "-t",
                args.targets.as_posix(),
                "-p",
                p,
                "-j",
                str(args.proc),
                "-o",
                full_opts,
                "-c" if args.custom else "",
            ]
            log_file = args.log / f"build-{compiler}-{p}.log"

            if args.compiler_path is not None:
                compiler_env = args.compiler_path / compiler
                cpp_compiler_env = args.compiler_path / cpp_compiler
            else:
                compiler_env = compiler
                cpp_compiler_env = cpp_compiler

            run_cmd(build_cmd, log_file, env={"CC": compiler_env, "CXX": cpp_compiler_env})

    # 0.5. Build targets with afl
    if args.all_stages or "build-afl" in args.stages:
        for p, targets in projects.items():
            project_dir_afl = args.targets / p / args.afl_compiler
            if not project_dir_afl.is_dir():
                log.debug(f"Directory {project_dir_afl} not found. Building {p} with {args.afl_compiler}...")
                build_afl_cmd = [
                    (base / "build-dataset" / "build.sh").as_posix(),
                    "-t",
                    args.targets.as_posix(),
                    "-p",
                    p,
                    "-j",
                    str(args.proc),
                    "-c",
                    "-o",
                    "0",
                ]

                log_file = args.log / f"build-afl-{p}.log"
                run_cmd(
                    build_afl_cmd,
                    log_file,
                    env={"CC": args.afl_compiler, "CXX": args.aflpp_compiler},
                )

    # 1. Download corpora
    if args.all_stages or "corpora" in args.stages:
        for p, targets in projects.items():
            for t in targets:
                cmd = [
                    "python3",
                    (base / "build-dataset" / "corpora.py").as_posix(),
                    "--project",
                    p,
                    "--fuzz-target",
                    t,
                ]
                log_file = args.log / f"corpora-{p}-{t}.log"
                run_cmd(cmd, log_file)

    # 2. Input minimization
    if args.all_stages or "minimize" in args.stages:
        for p, targets in projects.items():
            for t in targets:
                cmd = [
                    "python3",
                    (base / "build-dataset" / "minimize.py").as_posix(),
                    "--targets",
                    args.targets.as_posix(),
                    "--project",
                    p,
                    "--fuzz-target",
                    t,
                    "--proc",
                    str(args.proc),
                    "--compiler",
                    args.compiler,
                    "--cc-version",
                    args.cc_version,
                ]

                if args.debug:
                    cmd.append("--debug")

                log_file = args.log / f"minimize-{compiler}-{p}-{t}.log"
                run_cmd(cmd, log_file)

    # 3. Debug traces computation
    if args.all_stages or "traces" in args.stages:
        for p, targets in projects.items():
            for t in targets:
                cmd = [
                    "python3",
                    (base / "debug-quality" / "traces.py").as_posix(),
                    "--targets",
                    args.targets.as_posix(),
                    "--project",
                    p,
                    "--fuzz-target",
                    t,
                    "--proc",
                    str(args.proc),
                    "--compiler",
                    args.compiler,
                    "--cc-version",
                    args.cc_version,
                ]

                if args.debug:
                    cmd.append("--debug")

                log_file = args.log / f"traces-{compiler}-{p}-{t}.log"
                run_cmd(cmd, log_file)

    # 6. Polishing traces
    if args.all_stages or "static" in args.stages:
        for p, targets in projects.items():
            for t in targets:
                cmd = [
                    "python3",
                    (base / "debug-quality" / "static.py").as_posix(),
                    "--targets",
                    args.targets.as_posix(),
                    "--project",
                    p,
                    "--fuzz-target",
                    t,
                    "--compiler",
                    args.compiler,
                    "--cc-version",
                    args.cc_version,
                ]

                if args.debug:
                    cmd.append("--debug")

                log_file = args.log / f"static-{compiler}-{p}-{t}.log"
                run_cmd(cmd, log_file)

    # 7. Compute debuggability metrics
    if args.all_stages or "metrics" in args.stages:
        for project in projects:
            cmd = [
                "python3",
                (base / "debug-quality" / "metrics.py").as_posix(),
                "--targets",
                args.targets.as_posix(),
                "--project",
                project,
                "--compiler",
                args.compiler,
                "--cc-version",
                args.cc_version,
            ]

            if args.debug:
                cmd.append("--debug")

            log_file = args.log / f"metrics-{compiler}-{project}.log"
            run_cmd(cmd, log_file)

    # 8. Generate rankings
    if args.all_stages or "rankings" in args.stages:
        cmd = [
            "python3",
            (base / "compiler-tuning" / "rankings.py").as_posix(),
            "--targets",
            args.targets.as_posix(),
            "--compiler",
            args.compiler,
            "--cc-version",
            args.cc_version,
        ]

        if args.debug:
            cmd.append("--debug")

        if args.minimal:
            cmd.append("--minimal")

        log_file = args.log / f"rankings-{compiler}.log"
        run_cmd(cmd, log_file)

    if args.all_stages or "performance" in args.stages:
        cmd = [
            "python3",
            (base / "compiler-tuning" / "performance.py").as_posix(),
            "--targets",
            args.targets.as_posix(),
            "--compiler",
            args.compiler,
            "--cc-version",
            args.cc_version,
        ]

        if args.debug:
            cmd.append("--debug")

        log_file = args.log / f"performance-{compiler}.log"
        run_cmd(cmd, log_file)


if __name__ == "__main__":

    parser = ArgumentParser(
        description="Framework pipeline. Use the arguments --all or --stages to run the entire pipeline or only one or more specific stages.",
        formatter_class=ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "--targets",
        dest="targets",
        type=Path,
        help="Path to targets directory",
        default=Path(__file__).parent.resolve() / "dt-targets",
    )
    parser.add_argument(
        "--log",
        dest="log",
        type=Path,
        help="Log directory",
        default=Path(__file__).parent.resolve() / "dt-log",
    )
    mutually_exclusive_group = parser.add_mutually_exclusive_group(required=True)
    mutually_exclusive_group.add_argument(
        "--all-stages",
        dest="all_stages",
        action="store_true",
        help="Run the entire pipeline.",
        default=False,
    )
    mutually_exclusive_group.add_argument(
        "--stages",
        dest="stages",
        nargs="+",
        choices=[
            "build",
            "build-afl",
            "corpora",
            "minimize",
            "traces",
            "static",
            "metrics",
            "rankings",
            "performance",
        ],
        type=str,
        help="Specify one or more pipeline stage to run.",
        default=[],
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
        "--compiler-path",
        dest="compiler_path",
        type=Path,
        help="Path to compiler path for custom builds",
    )
    parser.add_argument(
        "--cpp-compiler",
        dest="cpp_compiler",
        choices=["g++", "clang++"],
        type=str,
        help="Compiler used to build target",
        default="g++",
    )
    parser.add_argument(
        "--afl-compiler",
        dest="afl_compiler",
        choices=["afl-clang-fast"],
        type=str,
        help="AFL++ compiler used to build target",
        default="afl-clang-fast",
    )
    parser.add_argument(
        "--aflpp-compiler",
        dest="aflpp_compiler",
        choices=["afl-clang-fast++"],
        type=str,
        help="AFL++ compiler used to build target",
        default="afl-clang-fast++",
    )
    parser.add_argument(
        "--cc-version",
        dest="cc_version",
        type=str,
        help="CC version to be tested",
        default="",
    )
    parser.add_argument(
        "--opts",
        dest="opts",
        type=str,
        help="Set of optimization configurations to be tested (':'-separated)",
        default="0:1:2:3:g",
    )
    parser.add_argument(
        "--custom",
        dest="custom",
        action="store_true",
        help="Enable custom optimization configurations",
        default=False,
    )
    parser.add_argument("--proc", dest="proc", type=int, help="Number of processes to use", default=1)
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

    if (args.compiler == "gcc" and args.cpp_compiler != "g++") or (
        args.compiler == "clang" and args.cpp_compiler != "clang++"
    ):
        args.cpp_compiler = ["g++", "clang++"][args.compiler != "gcc"]

    start_time = perf_counter()
    main(args)
    end_time = perf_counter()
    log.info(f"{end_time - start_time} seconds")
