from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parent / ".."))
from utils import run

pass_names = set()


def get_pass_arg(name, arg=True):
    if len(pass_names) == 0:
        for opt_level in ["0", "1", "2", "3"]:
            fuzzer_src = Path(__file__).resolve().parent / ".." / "misc" / "fuzzer-main.c"
            cmd = f"clang -O{opt_level} -mllvm -opt-bisect-limit=-1 {fuzzer_src} -o /dev/null"
            stderr = run.run_cmd(cmd, get_err=True)

            for line in stderr.split("\n"):
                if not "BISECT" in line:
                    continue

                line = line.split(") ")[1]
                line = line.split(" on ")[0]

                pass_arg = (
                    line.replace(" ", "_")
                    .replace("<", "_")
                    .replace(">", "_")
                    .replace("/", "_")
                    .replace("(", "_")
                    .replace("\\", "_")
                    .replace("-", "_")
                    .replace("::", "_")
                )

                pass_names.add((pass_arg, line))

    for pass_name in pass_names:
        if name == pass_name[0].lower():
            if arg:
                return pass_name[0]
            else:
                return pass_name[1]
    return ""
