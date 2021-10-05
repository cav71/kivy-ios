# replacement for sh package
# eg.
#  import kivy_ios.sh
#  sh = kivy_ios.sh.Sh()
#  sh.ls()
#  sh.git("status", sh.flag.JSON)
#  sh.xcodebuild("-sdk", "-version", "-json", sh.flag.JSON)

import logging
import enum
import subprocess
import json

from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class Flag(enum.Flag):
    ABORT = enum.auto()
    STRIP = enum.auto()
    JSON = enum.auto()
    SHPRINT = enum.auto()
    DEFAULT = ABORT | STRIP

    @classmethod
    def accumulate(cls, flags, default):
        # `or' all flags
        flags = [ f for f in flags if isinstance(f, cls) ]
        if not flags:
            return default
        result = flags[0]
        for a in flags[1:]:
            result |= a
        return result


class ShBase:
    flag = Flag(Flag.DEFAULT)

    @property
    def log(self):
        self._log = getattr(self, "_log", logger)
        return self._log 

    @log.setter
    def log(self, name):
        self._log = logging.getLogger(name) if name else logger

    def __init__(self, logname=None):
        self.log = logname

    def child(self, name):
        return self.__class__(f"{self._log.name}.{name}") 

    def __getattr__(self, cmd: str, *args, **kwargs) -> Any:
        def _fn(*largs):
            arguments = [cmd,] + [ str(a) for a in largs if not isinstance(a, self.flag.__class__) ]
            flags = self.flag.accumulate(largs, self.flag)

            self.log.debug("running: %s", arguments)
            p = subprocess.Popen(arguments,
                    encoding="utf-8",
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs)
            out, err = p.communicate()
            if flags and flags & self.flag.SHPRINT:
                for line in err.split("\n"):
                    self.log.debug(f"err> %s", line.rstrip())
                for line in out.split("\n"):
                    self.log.debug(f"out> %s", line.rstrip())

            if p.returncode:
                if flags & self.flag.ABORT:
                    raise RuntimeError(f"failed to execute {arguments}", out, err, p.returncode)
                return None
            
            if flags and flags & self.flag.STRIP:
                out = out.strip()
            if flags and flags & self.flag.JSON:
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
