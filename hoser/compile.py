from __future__ import annotations
from distutils.log import error
from enum import Enum
from typing import Any, Callable, Optional, Sequence, Union
from typing_extensions import Self
import dill
import dill.detect
import os

# Port types
class PortType(Enum):
    STREAM = "stream" # a stream of bytes
    INT = "int" # a 64 bit signed integer
    STRING = "string" # a string

    def from_class(c) -> PortType:
        if c == Stream:
            return PortType.STREAM
        elif c == String:
            return PortType.STRING
        else:
            raise ValueError(f"expected only hoser types (hoser.Stream, hoser.Str, ...), found type {c}")

class Port:
    def __init__(self, name: str, typ: PortType, dir: str) -> None:
        self.name = name
        self.typ = typ
        self.dir = dir

class Node:
    def __init__(self, name: str) -> None:
        self.name = name
        self.inports: dict[str, Port] = {}
        self.outports: dict[str, Port] = {}
        self.pipe: Optional[Pipe] = None # set when node is added to a pipe

    def add_in(self, name: str, typ: PortType) -> Port:
        self.inports[name] = Port(name, typ, "in")
        return self.inports[name]

    def add_out(self, name: str, typ: PortType) -> Port:
        self.outports[name] = Port(name, typ, "out")
        return self.outports[name]


class PortRef:
    def __init__(self, node: Node, port: str) -> None:
        self.node = node
        self.port = port

class Process(Node):
    def __init__(self, name: str, exe: str) -> None:
        super().__init__(name)
        self.name = name
        self.exe = exe
        self.args: list[Union[str, Port]] = []

class Variable(Node):
    def __init__(self, name: str, typ: PortType, default: Any = None) -> None:
        super().__init__(name)
        self.default = default
        self.add_in("i", typ)
        self.add_out("o", typ)
        self.dir = None

    @property
    def write(self) -> PortRef:
        return PortRef(node=self, port="i")

    @property
    def read(self) -> PortRef:
        return PortRef(node=self, port="o")

    def mark_sink(self):
        if self.dir == "spout":
            raise ValueError(f"variable {self.name} is already a spout, cannot also be a sink")
        self.dir = "sink"

    def mark_spout(self):
        if self.dir == "sink":
            raise ValueError(f"variable {self.name} is already a sink, cannot also be a spout")
        self.dir = "spout"

class Link:
    def __init__(self, fromproc: str, fromport: str, toproc: str, toport: str) -> None:
        self.fromnode = fromproc
        self.fromport = fromport
        self.tonode = toproc
        self.toport = toport

_proc_inst: dict[str, int] = {}
def next_instance(process: str) -> int:
    v = _proc_inst.get(process, 0)
    _proc_inst[process] = v + 1
    return v

class Pipe:
    """Pipe is a compiled Python pipe that can then be passed to marshal to turn it into a JSON representation."""
    def __init__(self, name: str, root_fn = Callable, parent: Optional[Pipe] = None) -> None:
        self.name = name
        self.root_fn = root_fn
        self.parent = parent
        self.children: list[Pipe] = []
        self.nodes: dict[str, Node] = {}
        self.links: list[Link] = []
        
    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        if len(_pipe_stack) > 0:
            self.parent = _pipe_stack[-1]
            self.parent.children.append(self)
        _pipe_stack.append(self)
        result = self.root_fn(*args, **kwargs)
        _pipe_stack.pop()
        return result

    def proc(self, name: str) -> Node:
        if not isinstance(self.nodes[name], Process):
            raise ValueError(f"{name} is not a process, {self.nodes[name]}")
        return self.nodes[name]

    def add_node(self, node: Node) -> Node:
        if node.name in self.nodes:
            raise ValueError(f"node with name '{node.name}' already exists in pipe")
        self.nodes[node.name] = node
        node.pipe = self
        return node

    def add_process(self, name: str, exe: str) -> Process:
        p = Process(name=name, exe=exe)
        self.add_node(p)
        return p

    def connect(self, src: PortRef, dst: PortRef):
        if src.node.name not in self.nodes:
            self.add_node(src.node)
        if dst.node.name not in self.nodes:
            self.add_node(dst.node)

        srcType = src.node.outports[src.port].typ
        dstType = dst.node.inports[dst.port].typ
        if srcType != dstType:
            raise ValueError(f"mismatched type between {src} -> {dst}, {srcType} != {dstType}")

        if isinstance(src.node, Variable):
            src.node.mark_spout()
        if isinstance(dst.node, Variable):
            dst.node.mark_sink()

        self.links.append(Link(src.node.name, src.port, dst.node.name, dst.port))

    def all_children(self) -> list[Pipe]:
        found: dict[str, Pipe] = {}
        self._resolve_children(found)
        return list(found.values())

    def _resolve_children(self, found: dict[str, Pipe]):
        for child in self.children:
            if child.name in found:
                cycle_desc = child.name
                parent = child.parent
                while parent is not None and parent.name != child.name:
                    cycle_desc = parent.name + " -> " + cycle_desc
                    parent = parent.parent
                raise ValueError("pipe cycle found: " + cycle_desc)
            found[child.name] = child
            child._resolve_children(found)

# Tracked by context so that the code doesn't have to constantly pass pipe around. Default
# pipe is returned if run in main program (outside of any hoser.pipe).
_pipe_stack: list[Pipe] = []
_default_pipe = Pipe(name="default")
def _active_pipe() -> Pipe:
    if len(_pipe_stack) > 0:
        return _pipe_stack[-1]
    else:
        return _default_pipe

def default_pipe() -> Pipe:
    return _default_pipe

class variableMap:
    def __getitem__(self, varname) -> Stream:
        pipe = _active_pipe()
        if varname in pipe.nodes:
            return Stream(pipe.nodes[varname], "o")
        return Stream(Variable(varname, PortType.STREAM), "o")

    def __setitem__(self, varname, value) -> None:
        pipe = _active_pipe()
        if varname in pipe.nodes:
            v = pipe.nodes[varname]
        else:
            v = pipe.add_node(Variable(varname, PortType.STREAM))
        pipe.connect(value, PortRef(v, "i"))

vars = variableMap()

def pipe(fn: Callable) -> Callable:
    return Pipe(name=fn.__name__, root_fn=fn)
   

def file(path: str = None, name: str = None) -> Stream:
    if name is None and path is not None:
        name = os.path.basename(path)
    if name is None:
        name = "file"+str(next_instance("file"))
    if path is not None:
        path = "file://"+path
    v = Variable(name, PortType.STREAM, default=path)
    return Stream(v, "o")

def string(value: str, name=None) -> String:
    if name is None:
        name = "string"+str(next_instance("string"))
    v = Variable(name, PortType.STRING, default=value)
    return String(v, "o")

class Stream(PortRef):
    def __init__(self, node: Node, port: str) -> None:
        super().__init__(node, port)

class String(PortRef):
    def __init__(self, node: Node, port: str) -> None:
        super().__init__(node, port)

class Input:
    def __init__(self, name: str, value: PortRef) -> None:
        self.name = name
        self.value = value

class Output:
    def __init__(self, name) -> None:
        self.name = name

"""
stdin refers to the stdin of the root hoser process that this pipeline is being run from
"""
stdin: Stream = Stream(node=Variable(name="stdin", typ=PortType.STREAM, default="stdin"), port="o")

"""
stdout will be written to the stdout of the root hoser process that this pipeline is being run for. If None,
then stdout will not be written to at all (default).
"""
stdout: Optional[Stream] = None

Returns = dict[str, Union[PortRef, list[PortRef]]]

def exec(exe: str, 
        args: Sequence[Union[str, Input, Output]], 
        stdin: Stream = None, 
        name: str = None, 
        stdout: bool = True,
        stderr: Union[bool, Callable[[Process, Stream], None]] = False) -> Any:
    pipe = _active_pipe()
    if name is None:
        name = exe + str(next_instance(exe))

    proc = Process(name=name, exe=exe)

    result = []
    # These are the args to the exe that was mentioned above
    if stdout:
        port = proc.add_out("stdout", PortType.STREAM)
        result.append(Stream(proc, port.name))

    
    if stderr and isinstance(stderr, bool):
        port = proc.add_out("stderr", PortType.STREAM)
        result.append(Stream(proc, port.name))
    elif callable(stderr):
        port = proc.add_out("stderr", PortType.STREAM)
        stderr(proc, Stream(proc, port.name))

    if stdin is not None:
        port = proc.add_in("stdin", PortType.STREAM)
        pipe.connect(stdin, PortRef(proc, port.name))
    
    for arg in args:
        if isinstance(arg, Input): # Input stream (connect ports)
            src = arg.value.node.outports[arg.value.port]
            port = proc.add_in(arg.name, src.typ)
            pipe.connect(arg.value, PortRef(proc, port.name))
            proc.args.append(port)
        elif isinstance(arg, Output):
            port = proc.add_out(arg.name, PortType.STREAM)
            result.append(Stream(proc, port.name))
            proc.args.append(port)
        elif isinstance(arg, str):
            proc.args.append(arg)
        else:
            raise ValueError(f"arg {arg} is not a valid type, must be only str, Input, or Output")
    
    if len(result) == 1:
        return result[0]
    else:
        return result

"""
A hoser function is a Python function that is serialized and packaged with the hos file to be
executed in a Python environment on the host. It is syntactic sugar for wrapping a Python function with
`python -c`.
"""

def fn(pyc: Callable) -> Callable:
    def inner(*args, stdin: Stream = None, **kwargs) -> Optional[Stream]:
        def _executor():
            pyc(*args, **kwargs)
        compiled = dill.dumps(_executor, byref=True, recurse=True)
        return exec("python", stdin=stdin, name=f"py:{pyc.__name__}", args=["-c", f"""
import dill
fn = dill.loads({compiled})
fn()
"""])
    return inner