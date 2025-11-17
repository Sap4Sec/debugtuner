import sys
import random
import tempfile
import re
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent / ".."))
from utils import log, run

from config import TIMEOUT


# ARGS: binary
DWARF = "llvm-dwarfdump --debug-line %s"
# ARGS: dbg_script_path - binary
GDB = "gdb -q -x %s %s"
LLDB = "lldb -s %s %s"

# When pagination is ON, GDB pauses at end of each screenful of its output and asks you whether to continue.
# Turning pagination off is an alternative to "set height unlimited".
# Setting width to "unlimited" prevents GDB from wrapping its output.
# Setting filename-display to absolute prints out the absolute path to the source file
# ARGS: gdb script, input file
GDB_SCRIPT_TEMPLATE = """python gdb.events.exited.connect(lambda x : gdb.execute("quit"))
set pagination off
set style enabled off
set filename-display absolute

%s

set width unlimited
run %s
quit
"""

# ARGS: break/tbreak, source, line
GDB_BP_TEMPLATE = """%s %s:%d
commands
    info locals
    continue
end
"""

# Setting the frame-format so that the absolute path to the source file is printed out
# For some reason, lldb shows ONLY multiple lines with a minimum of 2. The stop line count options set this limit (WTF LLDB)
# ARGS: lldb script, input file
# target stop-hook add -o 'script for thread in lldb.process: print("FUCK", thread.GetStopReason())'
LLDB_SCRIPT_TEMPLATE = """
settings set frame-format frame #${frame.index}: ${frame.pc}{ ${module.file.basename}{\`${function.name}}}{ at ${line.file.fullpath}:${line.number}}
settings set target.disable-aslr false
set set stop-line-count-before 1
set set stop-line-count-after 0

%s

run %s

quit
"""
# script import os; os._exit(0)

# The script to print the locals types is here
# ARGS: break/tbreak, source, line, breakpoint id
LLDB_BP_TEMPLATE = """%s set --file %s --line %d
break command add %d
    frame select
    frame var

    script locals = {}
    script for var in list(lldb.frame.arguments) + list(lldb.frame.variables): locals[var.name] = var.type.is_pointer
    script import json; print(f"[+] Locals type analysis: {json.dumps(locals)}")

    break delete %d
    continue
DONE
"""


def parse_dwarf(binary):
    """Parse the output of llvm-dwarfdump to extract a dict containing <source>:[<line>]
    Only statement lines are considered.

    Args:
        binary (Path): binary filepath

    Returns:
        dict: <source>:[<line>]
    """

    # Split line tables
    split_pattern = re.compile(r"debug_line\[0x[0-9a-fA-F]+\]")
    output = re.split(split_pattern, run.run_cmd(DWARF % (binary), get_output=True))[1:]

    # Get DWARF version
    dwarf_version = re.search(r"[vV]ersion:\s+(\d)", output[0]).group(1)
    start_idx = 1 if int(dwarf_version) < 5 else 0

    # Define source and line number patterns:
    # - source pattern has a group that matches the source code filename and a group that matches the directory index
    # - directories pattern matches the directory table
    # - line number pattern has two groups: (<line number>, <source index in the line table prologue>)
    source_pattern = re.compile(r"file_names\[ *\d+\]:\n +name: \"(.*)\"\n +dir_index: (\d+)")
    directories_pattern = re.compile(r"include_directories\[ *(\d+)\] = \"(.*)\"")
    # CA NOTE: for some reason on my pc the llvm-dwarfdump is slighly different and breaks the regex
    # we need to test which one is correct with the new llvm version in the docker
    linenumber_pattern = re.compile(r"0x[0-9a-fA-F]+ +(\d+) +\d+ +(\d+)(?: +\d+){2,3} +is_stmt")

    # Extract data
    source_lines_dict = dict()
    for table in output:
        sources = re.findall(source_pattern, table)
        lines = re.findall(linenumber_pattern, table)
        directories = {int(direct[0]): direct[1] for direct in re.findall(directories_pattern, table)}

        for i, source in enumerate(sources, start=start_idx):
            if int(source[1]) in directories:
                abs_source = f"{directories[int(source[1])]}/{source[0]}"
            else:
                abs_source = f"{source[0]}"

            source_lines_dict[abs_source] = [int(l[0]) for l in lines if l[1] == str(i)]

    source_lines_dict.pop("<built-in>", None)
    source_lines_dict = dict((source, list(set(lines))) for source, lines in source_lines_dict.items() if lines)
    return source_lines_dict


def run_dbg(binary, dbg_script, dbg, timeout):
    """Run a dbg script on a binary and returns the debug trace.

    Args:
        binary (Path): binary filepath
        dbg_script (str): dbg script
        dbg (str): debugger

    Returns:
        str: debug trace
    """
    output = ""

    cmd = [GDB, LLDB][dbg == "lldb"]

    with tempfile.TemporaryDirectory() as tmpdir:

        tmpfile = Path(tmpdir) / f"{str(random.randint(0, 2**32))}.dbg"
        with open(tmpfile, "w") as f:
            f.write(dbg_script)

        output = run.run_cmd(cmd % (tmpfile, binary), timeout=timeout, get_output=True)
    log.debug(output)
    return output


def parse_trace(trace, dbg):
    """Parse a debug trace and return variables info.

    Args:
        trace (str): debug trace
        dbg (str): debugger

    Returns:
        dict: {<source>:[<line>:{status}]}
    """
    output = {}
    functions = {}
    current_line = None
    trace_lines = trace.split("\n")

    for i, line in enumerate(trace_lines):
        line = line.strip()

        if dbg == "gdb":

            if line == "Program received signal SIGSEGV, Segmentation fault.":
                return -1
            if (
                "No locals" in line
                or "Inferior" in line
                or "Temporary" in line
                or "Reading" in line
                or len(line.split()) == 0
            ):
                continue

            # The first line/lines of info locals contains info about the tbreak, like "frame info" output in lldb
            # Then there is a line containing the line number and the source code instruction in the form "<line_number> <instruction>"
            # Finally, the last lines contain local variables names and value in the form "<name> = <value>"

            # Parsing "<line_number> <instruction>"
            if line.split()[0].isnumeric():
                if len(line.split()) == 1:
                    continue

                instruction = line.split(maxsplit=1)[1]
                # skip lines containing only "{" or "}"
                if instruction == "{" or instruction == "}":
                    current_line = False
                    continue

                current_line = line.split()[0]
                current_source = Path(
                    trace_lines[i - 1].split()[-1].split(":")[0]
                ).as_posix()  # read current source from preceding line
                current_function = (
                    trace_lines[i - 1].split(", ", maxsplit=1)[1].split()[0]
                )  # read current function from preceding line

                if current_source not in output:
                    output[current_source] = {}
                if current_line not in output[current_source]:
                    output[current_source][current_line] = {
                        "available": [],
                        "optimized_out": [],
                    }
                output[current_source][current_line]["function"] = current_function
                continue

            # Parsing local variables name and value in the form "<name> = <value>"
            if current_line and " = " in line:
                var_name = line.split(" = ", maxsplit=1)[0]
                value = line.split(" = ", maxsplit=1)[-1]
                if value == "<optimized out>":
                    output[current_source][current_line]["optimized_out"].append(var_name)
                else:
                    if var_name not in output[current_source][current_line]["available"]:
                        output[current_source][current_line]["available"].append(var_name)
        else:
            # in lldb the complete SIGSEGV message has some details that are not program independent
            # so let's check only the messages that are certain to be found

            if "stop reason = signal SIGSEGV" in line:
                return -1

            if (
                "lldb" in line
                or "Current" in line
                or "Breakpoint" in line
                or "Process" in line
                or "Command" in line
                or len(line.split()) == 0
            ):
                continue
            if (line.startswith("[") or line.startswith("*")) and not "[+] Locals type analysis: " in line:
                continue

            # After filtering out lines that are not relevant, there are only two possible cases: frame info or frame var

            # frame info
            # frame #0: [...] at <source>:<line>:<n>
            # if ":" in line.split()[-1] and not line.startswith("("):
            if re.match(r"^frame #\d:.*", line):
                # CA NOTE: this is not working because lldb prints "[inlined]"
                # when a function has been inlined, so the split is different
                if not "[inlined]" in line:
                    try:
                        current_line = line.split()[5].split(":")[-1]
                    except:
                        continue
                    current_source = Path(line.split()[5].split(":")[-2]).as_posix()

                else:
                    current_line = line.split()[7].split(":")[-1]
                    current_source = Path(line.split()[7].split(":")[-2]).as_posix()

                current_function = line.split()[3].split("`")[1]

                if trace_lines[i + 1].startswith("-> "):
                    instruction = " ".join(trace_lines[i + 1].split()[2:])
                    if instruction == "{" or instruction == "}":
                        current_line = None
                        continue

                if current_source not in output:
                    output[current_source] = {}
                if current_line not in output[current_source]:
                    output[current_source][current_line] = {
                        "available": [],
                        "optimized_out": [],
                        "not_available": [],
                    }
                output[current_source][current_line]["function"] = current_function
                continue

            # frame var
            if current_line and " = " in line and line.startswith("("):
                var_name = line.split(" = ")[0]
                if var_name.startswith("("):
                    var_name = var_name.split()[-1].strip()

                # CA NOTE: here this is wrong in case of multiline value definition.
                # But actually, it's not a problem since we kinda dropped the usage of values
                # https://stackoverflow.com/questions/31328204/lldb-one-line-output-for-print-and-display
                # see the link for a potential solution (not general)
                value = line.split(" = ")[-1].strip()
                if "optimized out" in value:
                    output[current_source][current_line]["optimized_out"].append(var_name)
                # "empty constant data" was not a message back in the day, let's work with it as if it is a not available variable
                elif "not available" in value or "empty constant data" in value or "could not evaluate" in value:
                    output[current_source][current_line]["not_available"].append(var_name)
                else:
                    output[current_source][current_line]["available"].append(var_name)

    for source, lines in output.items():
        for line in lines:
            # Sort each item for reproducibility
            output[source][line]["available"] = list(set(output[source][line]["available"]))
            output[source][line]["available"].sort()

            output[source][line]["optimized_out"] = list(set(output[source][line]["optimized_out"]))
            output[source][line]["optimized_out"].sort()
            if dbg == "lldb":
                output[source][line]["not_available"] = list(set(output[source][line]["not_available"]))
                output[source][line]["not_available"].sort()

            # remove inconsistencies
            for var in output[source][line]["available"]:
                if var in output[source][line]["optimized_out"]:
                    output[source][line]["optimized_out"].remove(var)
                if dbg == "lldb" and var in output[source][line]["not_available"]:
                    output[source][line]["not_available"].remove(var)
    functions = {key: functions[key] for key in sorted(functions.keys())}

    return output, functions


def get_variables(binary, input_filepath, dbg, timeout=TIMEOUT):
    """Prepare dbg script, get the debug trace calling run_dbg(),
    parse it through parse_trace() and return variables info.

    Args:
        binary (Path): binary filepath
        input_filepath (Path): passed as argv[1] to the binary
        dbg (str): debugger

    Returns:
        dict: {<source>:[<line>:{status}]}
    """
    log.debug(f"[{binary}] live variables computation: STARTED")
    lines_dict = parse_dwarf(binary)
    script_template = [GDB_SCRIPT_TEMPLATE, LLDB_SCRIPT_TEMPLATE][dbg == "lldb"]
    bps = []  # breakpoints

    for source, lines in lines_dict.items():
        if dbg == "lldb":
            start = len(bps)
            bps += [LLDB_BP_TEMPLATE % ("break", source, line, i + 1, i + 1) for i, line in enumerate(lines, start)]
        else:
            bps += [GDB_BP_TEMPLATE % ("tbreak", source, line) for line in lines]

    dbg_script = script_template % ("".join(bps), input_filepath)
    trace = run_dbg(binary, dbg_script, dbg, timeout)
    if not isinstance(trace, str):
        log.info(f"[{binary}] TIMEOUT EXPIRED")
        return {}, {}, {}
    parsing_result = parse_trace(trace, dbg)
    if parsing_result != -1:
        variables, functions = parsing_result
    else:
        log.info(f"[{binary}] SIGSEGV")
        return {}, {}, {}

    log.debug(f"[{binary}] live variables computation: COMPLETED")
    return variables, functions
