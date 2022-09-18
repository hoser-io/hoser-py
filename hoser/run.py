
import subprocess
import sys
import tempfile
import hoser
import os
import argparse


def run():
    """
    run will compile the given pipe and execute it using the hoser executable as a subprocess piping stdio
    
    :param pipe: Will be compiled and executed and the output ignored
    :param stdout: Pipe will be automatically piped to stdout
    """

    exit_when: hoser.Node = None
    if hoser.stdout is not None:
        stdoutVar = hoser.Variable(name="stdout", typ=hoser.PortType.STREAM, default="stdout")
        hoser.stdout.node.pipe.add_node(stdoutVar)
        hoser.stdout.node.pipe.connect(hoser.stdout, hoser.Stream(stdoutVar, "i"))
        exit_when = stdoutVar
     
    pipes = [hoser.default_pipe()]
    pipes += hoser.default_pipe().all_children()
    compiled = hoser.serialize(*pipes, exit_when=exit_when)

    parser = argparse.ArgumentParser(description="Compiles and runs hoser Python programs")
    parser.add_argument("-o", type=str, help='file path to output compiled JSON to')
    args, unknown = parser.parse_known_args()

    if args.o:
        with open(args.o, 'w') as tmp:
            tmp.write(compiled)
    else:
        with tempfile.NamedTemporaryFile() as tmp:
            tmp.write(compiled.encode("utf-8"))
            tmp.seek(0)
            result = subprocess.run(["hoser", "run"]+unknown+[tmp.name], stdin=sys.stdin, stderr=sys.stderr, stdout=sys.stdout)
            sys.exit(result.returncode)


def run_lines(lines: hoser.Stream, pipe: hoser.Pipe, err=False, varname="line"):
    """run_lines will execute 'pipe' for each line in the input passed as a variable called 'varname'"""
    return hoser.exec("hoser", args=["run", f"$SELF:{pipe.name}", "-sep", "\n", "-var", varname], stdin=lines, stderr=err)

        