# replacement for sh package
# eg.
#  import kivy_ios.sh
#  sh = kivy_ios.sh.Sh()
#  > simple call
#    sh.ls()
#  > filter the output and adds json parsing to the output 
#    sh.git("status", sh.flag.DEFAULT | sh.flag.JSON)
#  > don't aboort on failure
#    sh.ls("not-present", sh.flag.DEFAULT 
#  sh.xcodebuild("-sdk", "-version", "-json", sh.flag.JSON)

import os
import logging
import enum
import operator
import functools
import inspect
import subprocess
import json

from pathlib import Path
from typing import Any, Optional, Union, Callable


logger = logging.getLogger(__name__)


class ShBaseError(Exception):
    pass


class FileNotFound(ShBaseError):
    pass


class Flag(enum.IntFlag):
    ABORT = enum.auto()
    STRIP = enum.auto()
    JSON = enum.auto()
    SHPRINT = enum.auto()


class ShCommand:
    def __init__(self, cmd, flag, log):
        self.cmd = cmd
        self.flag = flag
        self.log = log

    def __call__(self, *args, **kwargs):
        arguments = [self.cmd,] + [ str(a) for a in args if not isinstance(a, Flag) ]
        flag = [ f for f in args if isinstance(f, Flag) ]
        assert len(flag) in {0, 1}, f"cannot pass more than one or no flags [{flag}]"
        flag = flag[0] if flag else self.flag

        if 'env' in kwargs:
            env = kwargs.pop("env")
        else:
            env = os.environ.copy()
            env["PATH"] = os.pathsep.join([".", *(env.get("PATH", "").split(os.pathsep))])

        self.log.debug("running: %s", arguments)
        p = subprocess.Popen(arguments,
                                encoding="utf-8", env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs)

        out, err = p.communicate()
        # similar to shprint
        if flag & Flag.SHPRINT:
            for line in err.split("\n"):
                self.log.debug(f"err> %s", line.rstrip())
            for line in out.split("\n"):
                self.log.debug(f"out> %s", line.rstrip())

        if p.returncode:
            if flag & Flag.ABORT:
                raise RuntimeError(f"failed to execute {arguments}", out, err, p.returncode)
            return None
            
        if flag & Flag.STRIP:
            out = out.strip()
        if flag & Flag.JSON:
            out = json.loads(out)
        return out


class ShBase:
    DEFAULT = Flag.STRIP | Flag.ABORT

    def Command(self, cmd):
        return self.__getattr__(cmd=cmd)

    @property
    def log(self):
        self._log = getattr(self, "_log", logger)
        return self._log 

    @log.setter
    def log(self, name):
        self._log = logging.getLogger(name) if name else logger

    def __init__(self, logname=None, flag=None):
        self.log = logname
        self.flag = self.DEFAULT if flag is None else flag

    def __getattr__(self, cmd: str) -> Any:
        return ShCommand(cmd, self.flag, self.log) 


class Sh(ShBase):
    def __getattr__(self, cmd: str, *args, **kwargs) -> Any:
        cmd = {
            "xcode_select": "xcode-select",
        }.get(cmd, cmd)
        return super(Sh, self).__getattr__(cmd, *args, **kwargs)

    def child(self, name):
        return self.__class__(logname=f"{self._log.name}.{name}", flag=self.flag)

    def which(self, arg: str, abort:bool=False) -> Optional[Path]:
        result = self.__getattr__("which")(arg, self.flag ^ Flag.ABORT)
        if abort:
            raise FileNotFound(f"cannot find executable {arg}")
        return Path(result) if result else None

    def cmd(self, name: Union[str, Path], abort: bool=True) -> Optional[Callable]:
        exe = self.which(name, abort=abort)
        if not exe:
            return
        def _fn(*args, **kwargs):
            return getattr(self, str(exe))(*args, **kwargs)
        return _fn


class SHPrint():
    def __init__(self, logname):
        self.logname = logname
        self.shs = {}
    def __getattr__(self, name):
        frame = inspect.stack()[1]
        module = inspect.getmodule(frame.frame)
        logname = f"{self.logname}.{module.__name__.rpartition('.')[2]}"
        if not logname in self.shs:
            self.shs[logname] = Sh(logname, Sh.DEFAULT | Flag.SHPRINT)
        return getattr(self.shs[logname], name)

