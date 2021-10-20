#!/usr/bin/env python
"""
Tool for compiling iOS toolchain
================================

This tool intend to replace all the previous tools/ in shell script.
"""
import os
import subprocess
import pathlib
import contextlib
import importlib
import json
import logging
import functools
import tempfile
import warnings
import dataclasses as dc

from types import ModuleType
from typing import Any, List, Optional, Dict, Union
from pathlib import Path

import attr
import click

logger = logging.getLogger(__name__)
sh_logging = logging.getLogger('sh')


def unravel(data: dict[str, Union[str, List[str]]]) -> Dict[str, Union[str, List[str]]]:
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

def config_guess():
    sh = Sh()
    system = sh.uname("-s")
    assert system == "Darwin", f"unsupported system [{system}]"

    arch = sh.uname("-m")
    assert arch == "arm64", f"unsupported arch [{arch}]"

    vendor = "apple"
    system = {
        "Darwin" : "darwin",
    }[system]
    arch = {
        "arm64" : "aarch64",
    }[arch]
    release = sh.uname("-r")
    class M:
        def __init__(self, tag):
            self.tag = tag
        def __eq__(self, pat):
            from fnmatch import fnmatch
            return fnmatch(self.tag, pat)
    return M(f"{arch}-{vendor}-{system}{release}")


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
            mod = importlib.import_module(name)
        recipe = mod.recipe
        recipe.recipe_dir = pathlib.Path(mod.__file__).parent
        return recipe   


class JsonStore:
    def __init__(self, path: Path):
        self.path = path
        self._data = None
    
    @property
    def data(self):
        if self._data is not None:
            return self._data
        self._data = {}
        with contextlib.suppress(IOError):
            with self.path.open("rb") as fp:
                self._data = json.load(fp)
        return self._data

    def sync(self):
        data = json.dumps(self.data)
        with self.path.open("w") as fp:
            fp.write(data)
    
    def __getitem__(self, key):
        return self.data[key]

    def __setitem__(self, key, value):
        self.data[key] = value
        self.sync()

    def __delitem__(self, key):
        del self.data[key]
        self.sync()

    def __contains__(self, item):
        return item in self.data

@dc.dataclass
class Sh:
    log: logging.Logger = dc.field(default_factory=lambda: logging.getLogger("sh"))

    def __getattr__(self, cmd: str, *args, **kwargs) -> Any:
        cmd = {
            "xcode_select": "xcode-select",
        }.get(cmd, cmd)
        def _fn(*largs):
            p = subprocess.Popen([cmd] + [str(c) for c in largs],
                    encoding="utf-8",
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            out, err = p.communicate()
            return out.rstrip()
        return _fn

    def which(self, arg: str) -> Optional[Path]:
        result = self.__getattr__("which")(arg)
        if result.strip():
            return pathlib.Path(result)


def get_runtime() -> Dict[str,Any]:
    sh = Sh()
    result = {}
    failures = {"missing": []}

    result["sdks"] = sdks = sh.xcodebuild("-showsdks").splitlines()

    # get the latest iphoneos
    iphoneos = [x for x in sdks if "iphoneos" in x]
    result["sdkver"] = sdkver = "<not-found>"
    if iphoneos:
        iphoneos = iphoneos[0].split()[-1].replace("iphoneos", "")
        result["sdkver"] = sdkver = iphoneos
    else:
        failures["missing"].append("No iphone SDK installed")
        
    # get the latest iphonesimulator version
    iphonesim = [x for x in sdks if "iphonesimulator" in x]
    result["sdksimver"] = sdksimver = "<not-found>"
    if iphonesim:
        iphonesim = iphonesim[0].split()[-1].replace("iphonesimulator", "")
        result["sdksimver"] = sdksimver = iphonesim
    else:
        failures["missing"].append("no iphonesimulator SDK installed")

    # get the path for Developer
    devpath = sh.xcode_select("-print-path").strip()
    result["devroot"] = devroot = pathlib.Path(f"{devpath}/Platforms/iPhoneOS.platform/Developer")

    # path to the iOS SDK
    result["iossdkroot"] = iossdkroot = devroot / f"SDKs/iPhoneOS{sdkver}.sdk"

    result["archs"] = archs = [] #[Arch64Simulator(ctx=ctx), Arch64IOS(ctx=ctx)]

    # path to some tools
    result["ccache"] = ccache = sh.which("ccache")
    result["cython"] = cython = sh.which("cython")
    if not cython:
        failures["missing"].append("requirement cython is not installed")

    # check the basic tools
    for tool in ("pkg-config", "autoconf", "automake", "libtool"):
        if sh.which(tool):
            continue
        failures["missing"].append(f"requirement {tool} is not installed")

    if any(failures.values()):
        msg = []
        for reason, values in failures.items():
            msg.append(reason)
            for value in values:
                msg.append(f"  {value}")
        raise RuntimeError("missing tools {'\n'.join(msg)}")

    result["use_pigz"] = sh.which('pigz')
    result["use_pbzip2"] = sh.which('pbzip2')
    result["num_cores"] = int(sh.sysctl('-n', 'hw.ncpu'))
    #self.num_cores = num_cores if num_cores else 4  # default to 4 if we can't detect
    return result

_dataclass = attr.s(slots=True, auto_attribs=True, frozen=True)


@_dataclass
class Flag:
    key : Union[str,Path]
    value : Optional[Any] = None
    pre : str = ""

    def __str__(self):
        value = self.key if self.value is None else f"{self.key}={self.value}"
        return f"{self.pre}{str(value)}"

    def __repr__(self):
        return f"<{self.__class__.__name__} pre={self.pre} key={self.key} at {hex(id(self))}>"
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


@attr.s(slots=True, auto_attribs=True)
class Arch:
    sdk : Optional[str] = None
    arch : Optional[str] = None
    triple: Optional[str] = None

    cflags: List[str] = dc.field(default_factory=list)
    cxxflags: List[str] = dc.field(default_factory=list)
    cppflags: List[Union[IFlag, DFlag]] = dc.field(default_factory=list)
    ldflags: List[LFlag] = dc.field(default_factory=list)
    ldlibs: List[lFlag] = dc.field(default_factory=list)

    _sysroot: Optional[Path] = None
    _ccsh: Optional[Any] = None
    _cxxsh: Optional[Any] = None

    @property
    def sysroot(self):
        self._sysroot = getattr(self, "_sysroot", None)
        if self._sysroot is None:
            self._sysroot = pathlib.Path(Sh().xcrun("--sdk", self.sdk, "--show-sdk-path").strip())
        return self._sysroot

    def __str__(self):
        return self.arch

    def get_env(self):
        sh = Sh()
        env = {}
        cc = [
            sh.xcrun("-find", "-sdk", self.sdk, "clang").strip(),
            "--sysroot", str(self.sysroot),
            "-arch", self.arch,
            "-pipe", "-no-cpp-precomp",
        ]
        cxx = [
            sh.xcrun("-find", "-sdk", self.sdk, "clang++").strip(),
            "--sysroot", str(self.sysroot),
            "-arch", self.arch,
            "-pipe", "-no-cpp-precomp",
        ]

        use_ccache = os.environ.get("USE_CCACHE", "1")
        ccache = None
        if use_ccache == "1":
            ccache = sh.which('ccache')
        if ccache:
            ccache = ccache.strip()
            env["USE_CCACHE"] = "1"
            env["CCACHE"] = ccache
            env.update({k: v for k, v in environ.items() if k.startswith('CCACHE_')})
            env.setdefault('CCACHE_MAXSIZE', '10G')
            env.setdefault('CCACHE_HARDLINK', 'true')
            env.setdefault(
                'CCACHE_SLOPPINESS',
                ('file_macro,time_macros,'
                 'include_file_mtime,include_file_ctime,file_stat_matches'))

        if not self._ccsh:
            self._ccsh = tempfile.NamedTemporaryFile()
            self._cxxsh = tempfile.NamedTemporaryFile()
            sh.chmod("+x", self._ccsh.name)
            sh.chmod("+x", self._cxxsh.name)
            self._ccsh.write(b'#!/bin/sh\n')
            self._cxxsh.write(b'#!/bin/sh\n')
            if ccache:
                logger.info("CC and CXX will use ccache")
                self._ccsh.write(
                    f"{ccache} {' '.join(cc)} \"$@\"\n".encode("utf8"))

                self._cxxsh.write(
                    f"{ccache} {' '.join(cxx)} \"$@\"\n".encode("utf8"))
            else:
                logger.info("CC and CXX will not use ccache")
                self._ccsh.write(
                    (cc + ' "$@"\n').encode("utf8"))
                self._cxxsh.write(
                    (cxx + ' "$@"\n').encode("utf8"))
            self._ccsh.flush()
            self._cxxsh.flush()

        env["CC"] = self._ccsh.name
        env["CXX"] = self._cxxsh.name
        env["AR"] = sh.xcrun("-find", "-sdk", self.sdk, "ar").strip()
        env["LD"] = sh.xcrun("-find", "-sdk", self.sdk, "ld").strip()
        env["OTHER_CFLAGS"] = " ".join(include_dirs)
        env["OTHER_LDFLAGS"] = " ".join(self.ldflags)
        env["CFLAGS"] = " ".join([
            "-O3",
            self.version_min
        ] + include_dirs)
        if self.sdk == "iphoneos":
            env["CFLAGS"] += " -fembed-bitcode"
        env["LDFLAGS"] = " ".join([
            "-arch", self.arch,
            # "--sysroot", self.sysroot,
            "-L{}/{}".format(self.ctx.dist_dir, "lib"),
            "-L{}/usr/lib".format(self.sysroot),
            self.version_min
        ])
        return env


@attr.s(slots=True, auto_attribs=True)
class Arch64Simulator(Arch):
    sdk : str = "iphonesimulator"
    arch : str = "x86_64"
    triple : str = "x86_64-apple-darwin13"
    version_min : str = "-miphoneos-version-min=9.0"


@attr.s(slots=True, auto_attribs=True)
class Arch64IOS(Arch):
    sdk: str = "iphoneos"
    arch : str= "arm64"
    triple : str = "aarch64-apple-darwin13"
    version_min : str = "-miphoneos-version-min=9.0"


@attr.s(slots=True, auto_attribs=True)
class Context:

    # the (current) working dir
    workdir: Path
    builddir: Path
    cachedir: Path
    prefix: Path

    # https://www.gnu.org/software/make/manual/html_node/Implicit-Variables.html
    cflags: List[str] = attr.ib(factory=list)
    cxxflags: List[str] = attr.ib(factory=list)

    cppflags: List[Union[IFlag, DFlag]] = attr.ib(factory=list)
    ldflags: List[LFlag] = attr.ib(factory=list)
    ldlibs: List[lFlag] = attr.ib(factory=list)

    env: Dict[str, str] = attr.ib(factory=dict)

    # the directory containing this module
    basedir: Path = pathlib.Path(__file__).parent
    recipesdir : Path = basedir / "recipes"

    @classmethod
    def click(cls):
        wrappers = [
            click.option("--workdir",
                         default=pathlib.Path().cwd()),
            click.option("--builddir",
                         default="{workdir}/build"),
            click.option("--cachedir",
                         default="{builddir}/cache"),
            click.option("--prefix",
                         default="{workdir}/dist"),

            click.option("--cflag", "cflags", multiple=True,
                         default=[]),
            click.option("--cxxflag", "cxxflags", multiple=True,
                         default=[]),

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
        def postprocess(kwargs):
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

            for key in {"cflags", "cxxflags"}:
                kw[key] = kwargs1[key]

            kw["cppflags"] = [
                *[ IFlag(flag) for flag in kwargs1["includes"] ],
                *[ DFlag(flag) for flag in kwargs1["defines"] ],
            ]

            kw["ldflags"] = [ LFlag(flag) for flag in kwargs1["ldflags"] ]
            kw["ldlibs"] = [ lFlag(flag) for flag in kwargs1["ldlibs"] ]
            return Context(**kw)

        return wrappers, postprocess

    # extra search paths
    #custom_recipes_paths: List[Path] = dc.field(default_factory=list)


    # # various flag/values
    # ccache : Optional[str] = None
    # cython : Optional[str] = None
    # sdkver : Optional[str] = None
    # sdksimver : Optional[str] = None
    # iossdkroot : Optional[Path] = None
    # so_suffix : Optional[str] = None
    # devroot : Optional[Path] = None
    # num_cores : Optional[int] = None
    #
    # archs: Optional[List["Arch"]] = None
    # _state : Optional[JsonStore] = None
    #
    # # @property
    # # def root_dir(self):
    # #     warnings.warn("Call to a deprecated ctx.rootdir, please use ctx.basedir",
    # #                   category=DeprecationWarning,
    # #                   stacklevel=2)
    # #     return self.basedir
    #
    # # @property
    # # def dist_dir(self):
    # #     warnings.warn("Call to a deprecated ctx.dist_dir, please use ctx.prefix",
    # #                   category=DeprecationWarning,
    # #                   stacklevel=2)
    # #     return self.prefix
    #
    # @property
    # def concurrent_make(self):
    #     return f"-j{self.num_cores}"
    #
    # @property
    # def concurrent_xcodebuild(self):
    #     return f"IDEBuildOperationMaxNumberOfConcurrentCompileTasks={self.num_cores}"
    #
    # @property
    # def state(self) -> JsonStore:
    #     if self._state is None:
    #         logger.debug("loading state from %s", self.dist_dir / "state.db")
    #         self._state = JsonStore(self.dist_dir / "state.db")
    #     return self._state
    #
    # @classmethod
    # def click(cls):
    #     fields = { f.name: f for f in dc.fields(cls) }
    #     wrappers = [
    #         click.option("--prefix", type=pathlib.Path, default=fields["prefix"].default),
    #         click.option("--cflag", "cflags", multiple=True, default=fields["cflags"].default_factory()),
    #         click.option("--cxxflag", "cxxflags", multiple=True, default=fields["cxxflags"].default_factory()),
    #
    #         # CPPFLAGS
    #         click.option("--include", "-I", "includes",
    #             type=pathlib.Path, multiple=True, show_default=True,
    #             default=fields["cppflags"].default),
    #         click.option("--define", "-D", "defines",
    #             multiple=True, show_default=True, default=[]),
    #
    #         # LDFLAGS/LDLIBS
    #         click.option("--ldflags", "-L", "ldflags",
    #             type=pathlib.Path, multiple=True, show_default=True,
    #             default=fields["ldflags"].default),
    #         click.option("--ldlibs",
    #             multiple=True, show_default=True, default=[]),
    #     ]
    #
    #     def postprocess(kwargs, ctx):
    #         ctx.cflags = kwargs.pop("cflags")
    #         ctx.cxxflags = kwargs.pop("cxxflags")
    #         ctx.cppflags  = [ IFlag(include).format(**kwargs) for include in kwargs.pop("includes") ]
    #         ctx.cppflags += [ DFlag(define) for define in kwargs.pop("defines") ]
    #         ctx.ldflags = [ LFlag(ldflag).format(**kwargs) for ldflag in kwargs.pop("ldflags") ]
    #         ctx.ldlibs = [ lFlag(ldlib) for ldlib in kwargs.pop("ldlibs")]
    #         ctx.prefix = kwargs.pop("prefix")
    #     return wrappers, postprocess
    #
    # def populate(self):
    #     for key, value in get_runtime().items():
    #         setattr(self, key, value)
    #
    #     for arch in [Arch64Simulator(), Arch64IOS()]:
    #         for key in ["cppflags", "ldflags", ]:
    #             getattr(arch, key).extend(p.format(**dc.asdict(self)) for p in getattr(self, key))
    #         self.archs.append(arch)
    #
    #     # remove the most obvious flags that can break the compilation
    #     self.env.pop("MACOSX_DEPLOYMENT_TARGET", None)
    #     self.env.pop("PYTHONDONTWRITEBYTECODE", None)
    #     self.env.pop("ARCHFLAGS", None)
    #     self.env.pop("CFLAGS", None)
    #     self.env.pop("LDFLAGS", None)




class RecipeManager:
    def __init__(self, ctx: Context, skip_list=None, **kwargs):
        self.ctx = ctx
        self.skip_list = skip_list or ['__pycache__']
        self.recipes : Dict[str, ModuleType] = {}

    def get_recipe(self, name: str) -> ModuleType:
        name, _, version = name.partition("==")
        if name in self.recipes:
            return self.recipes[name]
        recipe = loadr(f"kivy_ios.recipes.{name}")
        if not recipe:
            logger.info("Looking for recipe '{}' in custom_recipes_paths (if provided)".format(name))
            for custom_recipe_path in self.ctx.custom_recipes_paths:
                if custom_recipe_path.name != name:
                    continue
                recipe = loadr(name, custom_recipe_path / '__init__.py')
                if recipe:
                    logger.info("Custom recipe '{}' found in folder {}".format(name, custom_recipe_path))
                    break
        if not recipe:
            return
        recipe.init_after_import(self.ctx)
        recipe.version = recipe.version or version
        self.recipes[name] = recipe
        return self.recipes[name]

    def __iter__(self):
        for name, recipes in self.items():
            yield recipes

    def items(self):
        recipesdirs = [self.ctx.recipesdir, *self.ctx.custom_recipes_paths]
        for rdir in recipesdirs:
            for path in rdir.glob("*"):
                if not path.is_dir() or path.name in self.skip_list:
                    continue
                mod = self.get_recipe(path.name)
                if not mod:
                    continue
                yield path.name, self.get_recipe(path.name)


# CLI part
def common_options(fn):
    fn = click.option("-v", "--verbose", count=True,
            help="increase logging verbosity", show_default=False)(fn)
    fn = click.option("-q", "--quiet", count=True,
            help="decrease logging verbosity")(fn)
    # fn = click.option("--record", help="save the running config",
    #         type=click.Path(dir_okay=False, path_type=pathlib.Path))(fn)
    # fn = click.option("--replay", help="replay a running config",
    #         type=click.Path(dir_okay=False, path_type=pathlib.Path))(fn)

    # pulling the configurable options
    wrappers, postprocess = Context.click()
    for wrapper in wrappers:
        fn = wrapper(fn)

    @functools.wraps(fn)
    def _fn(*args, verbose, quiet, **kwargs):
        # logging
        level = verbose - quiet - 1
        level = logging.INFO if (level == 0) else logging.DEBUG if level > 0 else logging.WARNING 
        logging.basicConfig(
            format='[%(levelname)-8s] %(message)s',
            level=level)   
        # Quiet the loggers we don't care about
        logging.getLogger('sh').setLevel(logging.WARNING)

        kwargs["ctx"] = postprocess(kwargs)
        return fn(*args, **kwargs)
    return _fn

# host:
#    config.guess aarch64-apple-darwin20.6.0
#    sysconfig.get_platform() 'macosx-11.0-arm64'
# target: 

@click.group()
def main():
    pass


#@main.command()
#@click.option("--compact", is_flag=True, help="Produce a compact list suitable for scripting")
#@common_options
#def recipes(ctx, compact):
#    "List all the available recipes"
#    rm = RecipeManager(ctx)
#    if compact:
#        print(" ".join(sorted(str(r[0]) for r in rm)))
#    else:
#        for recipe in sorted(rm, key=lambda r: r.name.upper()):
#            if not recipe.version:
#                logger.debug("skipping %s without version", recipe.name)
#                continue
#            print(f"{recipe.name:<12} {recipe.version:<8}")
#
#
#@main.command(name="build_info")
#@common_options
#def build_info(ctx):
#    from pprint import pformat
#    print("Build Context")
#    print("-------------")
#    for attr in sorted(set(dir(ctx)) - {"populate"}):
#        if attr.startswith("_") or attr == "archs":
#            continue
#        if not callable(attr):
#            value = getattr(ctx, attr)
#            print(f"{attr}: {pformat(value)}")
#    for arch in ctx.archs:
#        ul = '-' * (len(str(arch))+6)
#        print("\narch: {}\n{}".format(str(arch), ul))
#        for attr in dir(arch):
#            if not attr.startswith("_"):
#                if not callable(attr) and attr not in ['arch', 'ctx', 'get_env']:
#                    print("{}: {}".format(attr, pformat(getattr(arch, attr))))
#        env = arch.get_env()
#        print("env ({}): {}".format(arch, pformat(env)))
#
#
#@main.command()
#@common_options
#def status():
#    ctx = Context()
#    rm = RecipeManager()
#    for recipe in sorted(rm.list_recipes()):
#        key = f"{recipe}.build_all"
#        keytime = f"{recipe}.build_all.at"
#        if key in ctx.state:
#            status = "Build OK (built at {})".format(ctx.state[keytime])
#        else:
#            status = "Not built"
#        print("{:<12} - {}".format(
#                recipe, status))
#
#
@main.command()
@common_options
def build(ctx):
    keys = [
        "workdir", "builddir", "cachedir", "prefix",
        "cflags", "cxxflags",
        "cppflags", "ldflags", "ldlibs",
    ]

    for key in keys:
        print(key, getattr(ctx, key))

if __name__ == "__main__":
    main()
