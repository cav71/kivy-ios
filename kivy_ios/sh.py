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

import logging
import enum
import operator
import subprocess
import json

from pathlib import Path
from typing import Any, Optional


logger = logging.getLogger(__name__)


class Flag(enum.IntFlag):
    ABORT = enum.auto()
    STRIP = enum.auto()
    JSON = enum.auto()
    SHPRINT = enum.auto()
    DEFAULT = ABORT | STRIP


class ShBase:
    @property
    def log(self):
        self._log = getattr(self, "_log", logger)
        return self._log 

    @log.setter
    def log(self, name):
        self._log = logging.getLogger(name) if name else logger

    def __init__(self, logname=None, flag=None):
        self.log = logname
        self.flag = Flag.DEFAULT if flag is None else flag

    def child(self, name):
        return self.__class__(f"{self._log.name}.{name}") 

    def __getattr__(self, cmd: str, *args, **kwargs) -> Any:
        def _fn(*args0, **kwargs0):
            arguments = [cmd,] + [ str(a) for a in args0 if not isinstance(a, Flag) ]
            flag = [ f for f in args0 if isinstance(f, Flag) ]
            assert len(flag) in {0, 1}, f"cannot pass more than one or no flags [{flag}]"
            flag = flag[0] if flag else self.flag

            self.log.debug("running (with flag=%s): %s", flag, arguments)
            p = subprocess.Popen(arguments,
                    encoding="utf-8",
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs0)
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
        return _fn


class Sh(ShBase):
    flag = Flag(Flag.STRIP)
    #def which(self, arg: str) -> Optional[Path]:
    #    result = self.__getattr__("which")(arg)
    #    if result.strip():
    #        return pathlib.Path(result)

    def __getattr__(self, cmd: str, *args, **kwargs) -> Any:
        cmd = {
            "xcode_select": "xcode-select",
        }.get(cmd, cmd)
        return super(Sh, self).__getattr__(cmd, *args, **kwargs)
