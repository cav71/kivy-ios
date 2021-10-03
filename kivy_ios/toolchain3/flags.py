import attr
from pathlib import Path
from typing import Any, Optional, Union

_dataclass = attr.s(slots=True, auto_attribs=True, frozen=True)


@_dataclass
class Flag:
    key : Union[str,Path]
    value : Optional[Any] = None
    pre : str = ""

    def __str__(self):
        value = self.key if self.value is None else f"{self.key}={self.value}"
        return f"{self.pre}{str(value)}"

    def format(self, **kwargs):
        return self.__class__(pathlib.Path(str(self.key).format(**kwargs)))

@_dataclass
class IFlag(Flag):
    pre : str = "-I"

@_dataclass
class LFlag(Flag):
    pre : str = "-L"

@_dataclass
class DFlag(Flag):
    pre : str = "-D"

@_dataclass
class lFlag(Flag):
    pre : str = "-l"
