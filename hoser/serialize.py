
import json
import re
from typing import Any, cast, Union
from hoser.compile import Link, Node, Pipe, Port, Process, Variable


def serialize(*args: Pipe, exit_when: Node = None) -> str:
    pipes = [*args]
    result: list[tuple[str, dict]] = []
    for pipe in pipes:
        result.append(("pipeline", {"id": pipe.name}))
        result += [_serialize_node(pipe, n) for _, n in pipe.nodes.items()]
        result += [_serialize_link(pipe, l) for l in pipe.links]

    if exit_when is not None and exit_when.pipe is not None:
        result.append(("exit", {"when": f"/{exit_when.pipe.name}/{exit_when.name}"}))

    lines = ""
    for r in result:
        lines += f"{r[0]} {json.dumps(r[1])}\n"
    return lines

def _serialize_node(pipe: Pipe, node: Node) -> tuple[str, dict]:
    if isinstance(node, Process):
        return _serialize_proc(pipe, cast(Process, node))
    elif isinstance(node, Variable):
        return _serialize_var(pipe, cast(Variable, node))
    raise ValueError(f"bad node: {node}")

def _serialize_proc(pipe: Pipe, proc: Process) -> tuple[str, dict]:
    return ("start", {"id": f"/{pipe.name}/{proc.name}", "exe": proc.exe, "argv": _serialize_args(proc.args)})

def _serialize_var(pipe: Pipe, var: Variable) -> tuple[str, dict]:
    if isinstance(var.default, str):
        if "file://" in var.default or var.default == "stdin" or var.default == "stdout":
            if var.dir == "sink":
                return ("set", {"id": f"/{pipe.name}/{var.name}", "write": var.default})
            else:
                return ("set", {"id": f"/{pipe.name}/{var.name}", "read": var.default})
        else:
            if var.dir == "spout":
                return ("set", {"id": f"/{pipe.name}/{var.name}", "text": var.default})
            else:
                raise ValueError(f"cannot turn variable {var.name} with text as value into sink")
    return ("set", {"id": f"/{pipe.name}/{var.name}"})

def _link_id(pipe: Pipe, node: str, port: str) -> str:
    if isinstance(pipe.nodes[node], Variable):
        return f"/{pipe.name}/{node}"
    else:
        return f"/{pipe.name}/{node}[{port}]"

def _serialize_link(pipe: Pipe, link: Link) -> tuple[str, dict]:
    return ("pipe", {
        "src": _link_id(pipe, link.fromnode, link.fromport),
        "dst": _link_id(pipe, link.tonode, link.toport),
    })

def _serialize_port(port: Port) -> dict[str, Any]:
    if port.dir == "in":
        return {"in": port.name}
    else:
        return {"out": port.name}

def _serialize_args(args: list[Union[Port, str]]) -> list[Union[str, dict]]:
    result: list[Union[str, dict]] = []
    for arg in args:
        if isinstance(arg, Port):
            result.append(_serialize_port(arg))
        else:
            result.append(arg)
    return result