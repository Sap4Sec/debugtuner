from __future__ import annotations
from argparse import ArgumentDefaultsHelpFormatter, ArgumentParser
import glob
from pathlib import Path
from subprocess import *
import time
from typing import List, Set

from ast_parser.ast import AST
from ast_parser.logger import Logger

CMD = "clang -w {} {} -fsyntax-only -Xclang -ast-dump=json {}"


def run_cmd(cmd, timeout=1200) -> CompletedProcess:
    try:
        return run(cmd.split(), stdout=PIPE, stderr=PIPE, timeout=timeout)
    except (CalledProcessError, TimeoutExpired):
        return None


def parse_includes(code: str) -> Set[str]:
    headers = []
    for line in code:
        if "#include" in line.replace(" ", ""):
            if not '"' in line and not "<" in line:
                continue
            sp = [("<", ">"), ('"', '"')][">" not in line]
            header = line.split(sp[0])[1].split(sp[1])[0]

            # NOTE: pg_query is shit
            if header == "string.h":
                continue

            headers.append(header)
    return set(headers)


def find_include_dirs(c_file: Path, directory: Path) -> Set[Path]:
    if directory is None:
        return set()

    workqueue = parse_includes(open(c_file).readlines())
    computed = set()

    hdr_directories = set()
    while len(workqueue) > 0:
        header = workqueue.pop()
        if header in computed:
            continue

        computed.add(header)

        hdr_name = header.split("/")[-1]
        found = list(
            map(
                lambda x: Path(x),
                glob.glob((directory / "**" / f"*{hdr_name}").as_posix(), recursive=True),
            )
        )

        for found_header in found:
            if header in found_header.as_posix():
                hdr_directory = found_header.parent
                for _ in range(header.count("/")):
                    hdr_directory = hdr_directory.parent

                if "os400" in hdr_directory.as_posix():
                    continue
                hdr_directories.add(hdr_directory)

            workqueue |= parse_includes(open(found_header).readlines())

    return hdr_directories


def parse_ast(c: Path, dir: Path, out: Path = None, inc: List[Path] = [], prep: List[str] = []) -> AST:

    included_headers = find_include_dirs(c, dir) | set(inc)

    # shit here <- to solve this, improve include finder to avoid adding paths for standard libraries
    # when -I is used to be able to use <>, this is not simple
    if dir is not None:
        if "libssh" in dir.as_posix():
            to_rem = []
            for include in included_headers:
                if "include/libssh" in include.as_posix():
                    to_rem.append(include)
            for t in to_rem:
                included_headers.remove(t)

    includes = list(map(lambda x: f"-I {x}", included_headers))
    preproc = list(map(lambda x: f"-D{x}", set(prep)))

    # print(CMD.format(" ".join(includes), " ".join(preproc), c))

    process = run_cmd(CMD.format(" ".join(includes), " ".join(preproc), c))
    if process.returncode != 0:
        hdr = parse_includes(process.stderr.decode().split("\n"))
        print(process.stderr.decode())
        Logger.log().error(f"Unable to generate AST for {c}: missing {hdr}")
        exit(-1)

    ast = AST(process.stdout.decode())

    if out is not None:
        ast.dump(out)
    return ast


def main(args):
    if args.debug:
        Logger.set_debug()

    start = time.perf_counter()
    ast = parse_ast(args.c_file, args.directory, args.out, args.include, args.prep)
    end = time.perf_counter()

    for func in ast:
        Logger.log().debug(f"\n{func}")

    # TEST CODE HERE

    Logger.log().info(f"Elapsed time: {end - start} s")


if __name__ == "__main__":
    parser = ArgumentParser(description="LLVM AST PARSER", formatter_class=ArgumentDefaultsHelpFormatter)

    parser.add_argument(
        "--cfile",
        dest="c_file",
        type=Path,
        help="Input C file",
        required=True,
    )
    parser.add_argument(
        "--directory",
        dest="directory",
        type=Path,
        help="Input directory (if project directory is needed)",
    )
    parser.add_argument(
        "--include",
        dest="include",
        nargs="+",
        type=str,
        help="Include directories (if custom include directories are needed)",
        default=[],
    )
    parser.add_argument(
        "--prep",
        dest="prep",
        nargs="+",
        type=str,
        help="Preprocessor variables to be defined (if needed)",
        default=[],
    )
    parser.add_argument("--out", dest="out", type=Path, help="Path to AST output pickle file")
    parser.add_argument(
        "--debug",
        dest="debug",
        action="store_true",
        default=False,
        help="Enable debug prints",
    )

    args = parser.parse_args()
    main(args)
