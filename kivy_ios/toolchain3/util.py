import os
import pathlib
import contextlib
import logging
import json
import subprocess
import enum
import tempfile

from pathlib import Path
from typing import Any, Union, List, Dict, Optional, Iterable
from types import  ModuleType

import attr


def logtype(txt):
    return logging.getLogger(txt) if isinstance(txt, str) else txt


@attr.s
class ShBase:
    class flag(enum.Flag):
        ABORT = enum.auto()
        STRIP = enum.auto()
        JSON = enum.auto()
        DEFAULT = ABORT | STRIP

        @classmethod
        def accumulate(cls, flags, default):
            flags = [ f for f in flags if isinstance(f, cls) ]
            if not flags:
                return default
            result = flags[0]
            for a in flags[1:]:
                result |= a
            return result

    log: logging.Logger = attr.ib(factory=lambda: logging.getLogger("sh"), converter=logtype)

    def __getattr__(self, cmd: str, *args, **kwargs) -> Any:
        def _fn(*largs):
            arguments = [cmd,] + [ str(a) for a in largs if not isinstance(a, self.flag) ]
            flags = self.flag.accumulate(largs, self.flag.DEFAULT)

            self.log.debug("running: %s", arguments)
            p = subprocess.Popen(arguments,
                    encoding="utf-8",
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            out, err = p.communicate()
            if flags & self.flag.ABORT and p.returncode:
                raise RuntimeError(f"failed to execute {arguments}", out, err, p.return_code)
            
            if flags and flags & self.flag.STRIP:
                out = out.strip()
            if flags and flags & self.flag.JSON:
                out = json.loads(out)

            return out
        return _fn

@attr.s
class Sh(ShBase):
    def which(self, arg: str) -> Optional[Path]:
        result = self.__getattr__("which")(arg)
        if result.strip():
            return pathlib.Path(result)

    def __getattr__(self, cmd: str, *args, **kwargs) -> Any:
        cmd = {
            "xcode_select": "xcode-select",
        }.get(cmd, cmd)
        return super(Sh, self).__getattr__(cmd, *args, **kwargs)


def loadr(name: str, path: Optional[Path] = None) -> Optional[ModuleType]:
    from importlib import import_module
    from importlib.util import (
        spec_from_file_location,
        module_from_spec,
    )

    with contextlib.suppress(ImportError):
        if path:
            spec = spec_from_file_location(name, path)
            mod = module_from_spec(spec)
            spec.loader.exec_module(mod)
        else:
            mod = import_module(name)
        recipe = mod.recipe
        recipe.recipe_dir = Path(mod.__file__).parent
        if not recipe.__doc__:
            recipe.__doc__ = f"recipe for {recipe.name}"
        return recipe   


def unravel(data: dict[str, Union[str, List[str]]]) -> Dict[str, Union[str, List[str]]]:
    """recursively resolve a data dict 
    
    Eg: 
        >>> urnavel({ "a": "hello", "b": "{a} world"})
        { "a": "hello", "b": "hello world"}
    """
    def _iter(value, data):
        pre = value
        post = value.format(**data)
        while pre != post:
            pre = post
            post = value.format(**data)
        return post

    original = data.copy()
    for key, value in data.items():
        if isinstance(value, str):
            data[key] = _iter(value, data)
        elif isinstance(value, (list, tuple)):
            data[key] = [ _iter(v, data) for v in value ]

    while original != data:
        original = data.copy()
        unravel(data)
    return original
    def _iter(value, data):
        pre = value
        post = value.format(**data)
        while pre != post:
            pre = post
            post = value.format(**data)
        return post

    original = data.copy()
    for key, value in data.items():
        if isinstance(value, str):
            data[key] = _iter(value, data)
        elif isinstance(value, (list, tuple)):
            data[key] = [ _iter(v, data) for v in value ]

    while original != data:
        original = data.copy()
        unravel(data)
    return original


@contextlib.contextmanager
def cdinto(target: Path=None, remove: Optional[bool] = None):
    from shutil import rmtree
    remove = not bool(target) if remove is None else remove
    target = tempfile.mkdtemp()
    try:
        oldpwd = pathlib.Path.cwd()
        os.chdir(target)   
        yield oldpwd
    finally:
        os.chdir(oldpwd)
        if remove:
            breakpoint()
            rmtree(target, ignore_errors=True)


def rstrips(txt: str, values: Union[Iterable, str]) -> str:
    values = [values,] if isinstance(values, str) else values
    result = txt
    for value in values:
        if result.endswith(value):
            result = result[:-len(value)]
    return result

