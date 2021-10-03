import pathlib
import functools
from pathlib import Path
from typing import List, Union, Dict

import click
import attr

from .util import unravel
from .flags import IFlag, LFlag, DFlag, lFlag

from kivy_ios import recipes


@attr.s(slots=True, auto_attribs=True)
class GnuFlags:
    # https://www.gnu.org/software/automake/manual/html_node/Cross_002dCompilation.html
    host : str = ""

    # https://www.gnu.org/software/make/manual/html_node/Implicit-Variables.html
    cflags: List[str] = attr.ib(factory=list)
    cxxflags: List[str] = attr.ib(factory=list)

    cppflags: List[Union[IFlag, DFlag]] = attr.ib(factory=list)

    ldflags: List[LFlag] = attr.ib(factory=list)
    ldlibs: List[lFlag] = attr.ib(factory=list)


@attr.s(slots=True, auto_attribs=True)
class Context:

    # the (current) working dir
    workdir: Path

    # we build here
    builddir: Path

    # cache artifacts here
    cachedir: Path

    # destination
    prefix: Path

    gnuflags: GnuFlags

    env: Dict[str, str] = attr.ib(factory=dict)

    # the directory containing this module
    basedir: Path = pathlib.Path(__file__).parent
    recipesdir : Path = pathlib.Path(recipes.__file__).parent


def context_args(fn):
    wrappers = [
        click.option("--workdir", show_default=True,
                     default=pathlib.Path().cwd()),
        click.option("--builddir", show_default=True,
                     default="{workdir}/build"),
        click.option("--cachedir", show_default=True,
                     default="{builddir}/cache"),
        click.option("--prefix", show_default=True,
                     default="{workdir}/dist"),

        click.option("--cflag", "cflags", multiple=True,
                     show_default=True, default=[]),
        click.option("--cxxflag", "cxxflags", multiple=True,
                     show_default=True, default=[]),

        # CPPFLAGS
        click.option("--include", "-I", "includes",
            multiple=True, show_default=True, default=["{prefix}/include"]),
        click.option("--define", "-D", "defines",
            multiple=True, show_default=True, default=[]),

        # # LDFLAGS/LDLIBS
        click.option("--ldflags", "-L", "ldflags",
            multiple=True, show_default=True,
            default=["{prefix}/lib"]),
        click.option("--ldlibs",
            multiple=True, show_default=True, default=[]),
    ]

    for wrapper in wrappers:
        fn = wrapper(fn) 

    @functools.wraps(fn)
    def _fn(ctx, *args, **kwargs):
        ctx.obj = instance(kwargs)
        return fn(ctx, **kwargs)
    return _fn


def instance(kwargs):
    kwargs1 = unravel(kwargs)

    keys = {"workdir", "builddir", "cachedir", "prefix",
            "cflags", "cxxflags",
            "includes", "defines", "ldflags", "ldlibs",
            }
    for key in keys:
        kwargs.pop(key)

    kw = {}
    for key in {"workdir", "builddir", "cachedir", "prefix",}:
        kw[key] = pathlib.Path(kwargs1[key])

    gnukw = {}
    for key in {"cflags", "cxxflags"}:
        gnukw[key] = kwargs1[key]

    gnukw["cppflags"] = [
        *[ IFlag(flag) for flag in kwargs1["includes"] ],
        *[ DFlag(flag) for flag in kwargs1["defines"] ],
    ]

    gnukw["ldflags"] = [ LFlag(flag) for flag in kwargs1["ldflags"] ]
    gnukw["ldlibs"] = [ lFlag(flag) for flag in kwargs1["ldlibs"] ]

    kw["gnuflags"] = GnuFlags(**gnukw)
    return Context(**kw)

