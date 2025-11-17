#!/usr/bin/env python3

import subprocess
from pathlib import Path
from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
import sys

sys.path.append(str(Path(__file__).resolve().parent / ".."))
from utils import log


def main(args):
    helper = args.oss_fuzz / "infra" / "helper.py"
    cmd = [
        "python3",
        helper.as_posix(),
        "download_corpora",
        "--public",
        args.project,
        "--fuzz-target",
        args.fuzz_target,
    ]
    log.info(" ".join(cmd))
    result = subprocess.run(cmd)
    result.check_returncode()


if __name__ == "__main__":

    parser = ArgumentParser(
        description="Download oss-fuzz corpora for the selected target.",
        formatter_class=ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "--oss-fuzz",
        dest="oss_fuzz",
        type=Path,
        help="Path to the oss-fuzz directory",
        default=Path(__file__).parent.resolve() / ".." / "dt-projects" / "oss-fuzz",
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
    main(args)
