from subprocess import *


def run_cmd(cmd, debug=False, get_output=False, get_err=False, timeout=1200, outfile=None):
    r = None
    try:
        if debug:
            r = run(cmd.split(), timeout=timeout)
            r.check_returncode()
        elif get_output:
            r = run(cmd.split(), stdout=PIPE, stderr=PIPE, timeout=timeout)
            return r.stdout.decode()
        elif get_err:
            r = run(cmd.split(), stdout=PIPE, stderr=PIPE, timeout=timeout)
            return r.stderr.decode()
        elif outfile:
            r = run(cmd.split(), stdout=outfile, stderr=PIPE, timeout=timeout)
            r.check_returncode()
        else:
            r = run(cmd.split(), stdout=DEVNULL, stderr=DEVNULL, timeout=timeout)
            r.check_returncode()
    except (CalledProcessError, TimeoutExpired):
        if r == None:
            return 1
        if r.returncode == 254:
            return 2
        return 1
    return
