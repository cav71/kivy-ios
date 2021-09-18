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
from typing import Any, List, Optional, Dict
from pathlib import Path

import click

logger = logging.getLogger(__name__)
sh_logging = logging.getLogger('sh')


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


def get_runtime(ctx: Context) -> Dict[str,Any]:
    sh = Sh()
    result = {}
    result["sdks"] = sdks = sh.xcodebuild("-showsdks").splitlines()

    # get the latest iphoneos
    iphoneos = [x for x in sdks if "iphoneos" in x]
    result["sdkver"] = sdkver = "<not-found>"
    if iphoneos:
        iphoneos = iphoneos[0].split()[-1].replace("iphoneos", "")
        result["sdkver"] = sdkver = iphoneos
    else:
        logger.error("No iphone SDK installed")
        ok = False
        
    # get the latest iphonesimulator version
    iphonesim = [x for x in sdks if "iphonesimulator" in x]
    result["sdksimver"] = sdksimver = "<not-found>"
    if not iphonesim:
        iphonesim = iphonesim[0].split()[-1].replace("iphonesimulator", "")
        result["sdksimver"] = sdksimver = iphonesim
    else:
        ok = False
        logger.error("Error: No iphonesimulator SDK installed")

    # get the path for Developer
    devpath = sh.xcode_select("-print-path").strip()
    result["devroot"] = devroot = pathlib.Path(f"{devpath}/Platforms/iPhoneOS.platform/Developer")

    # path to the iOS SDK
    result["iossdkroot"] = iossdkroot = devroot / f"SDKs/iPhoneOS{sdkver}.sdk"

    result["archs"] = archs = [Arch64Simulator(ctx=ctx), Arch64IOS(ctx=ctx)]

    # path to some tools
    result["ccache"] = ccache = sh.which("ccache")
    result["cython"] = cython = sh.which("cython")
    if not cython:
        ok = False
        logger.error("Missing requirement: cython is not installed")

    # check the basic tools
    for tool in ("pkg-config", "autoconf", "automake", "libtool"):
        if sh.which(tool):
            continue
        logger.error("Missing requirement: %s is not installed", tool)
        ok = False

    if not ok:
        raise RuntimeError("missing tools")

    self.use_pigz = sh.which('pigz')
    self.use_pbzip2 = sh.which('pbzip2')
    self.num_cores = int(sh.sysctl('-n', 'hw.ncpu'))
    #self.num_cores = num_cores if num_cores else 4  # default to 4 if we can't detect

    # remove the most obvious flags that can break the compilation
    self.env.pop("MACOSX_DEPLOYMENT_TARGET", None)
        self.env.pop("PYTHONDONTWRITEBYTECODE", None)
        self.env.pop("ARCHFLAGS", None)
        self.env.pop("CFLAGS", None)
        self.env.pop("LDFLAGS", None)
        return self
    pass


@dc.dataclass
class Context:
    env = os.environ.copy()

    # the directory containing this module
    basedir: Path = pathlib.Path(__file__).parent

    # the (current) working dir
    workdir: Path = pathlib.Path().cwd()

    prefix: Path = workdir / "dist"
    builddir: Path = workdir / "build"

    # extra search paths
    recipesdir : Path = basedir / "recipes"
    custom_recipes_paths: List[Path] = dc.field(default_factory=list)

    include_dir : Path = workdir / "dist/include"
    include_dirs : List[Path] = dc.field(default_factory=list)

    cache_dir : Path = workdir / ".cache"
    build_dir : Path = workdir / "build"
    install_dir : Path = workdir / "dist/root"
    ccache : Optional[str] = None
    cython : Optional[str] = None
    sdkver : Optional[str] = None
    sdksimver : Optional[str] = None
    iossdkroot : Optional[Path] = None
    so_suffix : Optional[str] = None
    devroot : Optional[Path] = None

    num_cores : Optional[int] = None

    archs: Optional[List["Arch"]] = None
    _state : Optional[JsonStore] = None


    @property
    def root_dir(self):
        warnings.warn("Call to a deprecated ctx.rootdir, please use ctx.basedir",
                      category=DeprecationWarning,
                      stacklevel=2)
        return self.basedir

    @property
    def dist_dir(self):
        warnings.warn("Call to a deprecated ctx.dist_dir, please use ctx.prefix",
                      category=DeprecationWarning,
                      stacklevel=2)
        return self.prefix

    @property
    def concurrent_make(self):
        return f"-j{self.num_cores}"

    @property
    def concurrent_xcodebuild(self):
        return f"IDEBuildOperationMaxNumberOfConcurrentCompileTasks={self.num_cores}"

    @property
    def state(self) -> JsonStore:
        if self._state is None:
            logger.debug("loading state from %s", self.dist_dir / "state.db")
            self._state = JsonStore(self.dist_dir / "state.db")
        return self._state

    @classmethod
    def click(cls):
        fields = { f.name: f for f in dc.fields(cls) }
        wrappers = {}
        for name in ["prefix", "workdir", "ccache"]:
            wrappers[name] = click.option(f"--{name}", type=pathlib.Path, default=fields[name].default)
        for name in ["num_cores",]:
            wrappers[name] = click.option(f"--{name.replace('_', '-')}", type=int, default=fields[name].default)
            
        return wrappers

    def populate(self):
        sh = Sh()
        sdks = sh.xcodebuild("-showsdks").splitlines()

        # get the latest iphoneos
        iphoneos = [x for x in sdks if "iphoneos" in x]
        if not iphoneos:
            logger.error("No iphone SDK installed")
            ok = False
        else:
            iphoneos = iphoneos[0].split()[-1].replace("iphoneos", "")
            self.sdkver = iphoneos
        
        # get the latest iphonesimulator version
        iphonesim = [x for x in sdks if "iphonesimulator" in x]
        if not iphonesim:
            ok = False
            logger.error("Error: No iphonesimulator SDK installed")
        else:
            iphonesim = iphonesim[0].split()[-1].replace("iphonesimulator", "")
            self.sdksimver = iphonesim

        # get the path for Developer
        self.devroot = pathlib.Path("{}/Platforms/iPhoneOS.platform/Developer".format(
            sh.xcode_select("-print-path").strip()))

        # path to the iOS SDK
        self.iossdkroot = self.devroot / f"SDKs/iPhoneOS{self.sdkver}.sdk"

        self.archs = [Arch64Simulator(ctx=self), Arch64IOS(ctx=self)]

        # path to some tools
        ok = True
        self.ccache = sh.which("ccache")
        self.cython = sh.which("cython")
        if not self.cython:
            ok = False
            logger.error("Missing requirement: cython is not installed")

        # check the basic tools
        for tool in ("pkg-config", "autoconf", "automake", "libtool"):
            if sh.which(tool):
                continue
            logger.error("Missing requirement: %s is not installed", tool)
            ok = False

        if not ok:
            logger.warning("aborting ..")
            sys.exit(1)

        self.use_pigz = sh.which('pigz')
        self.use_pbzip2 = sh.which('pbzip2')
        self.num_cores = int(sh.sysctl('-n', 'hw.ncpu'))
        #self.num_cores = num_cores if num_cores else 4  # default to 4 if we can't detect

        # remove the most obvious flags that can break the compilation
        self.env.pop("MACOSX_DEPLOYMENT_TARGET", None)
        self.env.pop("PYTHONDONTWRITEBYTECODE", None)
        self.env.pop("ARCHFLAGS", None)
        self.env.pop("CFLAGS", None)
        self.env.pop("LDFLAGS", None)
        return self


@dc.dataclass
class Arch:
    ctx: Optional[Context] = None
    sdk : Optional[str] = None
    arch : Optional[str] = None
    triple: Optional[str] = None

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

    @property
    def include_dirs(self):
        return [
            "{}/{}".format(
                self.ctx.include_dir,
                d.format(arch=self))
            for d in self.ctx.include_dirs]

    def get_env(self):
        include_dirs = [
            "-I{}/{}".format(
                self.ctx.include_dir,
                d.format(arch=self))
            for d in self.ctx.include_dirs]
        include_dirs.append(f"-I{self.ctx.dist_dir / 'include' / self.arch}")

        env = {}
        sh = Sh()
        cc = sh.xcrun("-find", "-sdk", self.sdk, "clang").strip()
        cxx = sh.xcrun("-find", "-sdk", self.sdk, "clang++").strip()

        # we put the flags in CC / CXX as sometimes the ./configure test
        # with the preprocessor (aka CC -E) without CFLAGS, which fails for
        # cross compiled projects
        flags = " ".join([
            "--sysroot", str(self.sysroot),
            "-arch", self.arch,
            "-pipe", "-no-cpp-precomp",
        ])
        cc += " " + flags
        cxx += " " + flags

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
                    (ccache + ' ' + cc + ' "$@"\n').encode("utf8"))
                self._cxxsh.write(
                    (ccache + ' ' + cxx + ' "$@"\n').encode("utf8"))
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
        env["OTHER_LDFLAGS"] = " ".join([
            "-L{}/{}".format(self.ctx.dist_dir, "lib"),
        ])
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


@dc.dataclass
class Arch64Simulator(Arch):
    sdk : str = "iphonesimulator"
    arch : str = "x86_64"
    triple : str = "x86_64-apple-darwin13"
    version_min : str = "-miphoneos-version-min=9.0"


@dc.dataclass
class Arch64IOS(Arch):
    sdk: str = "iphoneos"
    arch : str= "arm64"
    triple : str = "aarch64-apple-darwin13"
    version_min : str = "-miphoneos-version-min=9.0"


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
    fn = click.option("-v", "--verbose", count=True)(fn)
    fn = click.option("-q", "--quiet", count=True)(fn)

    # pulling the configurable options
    wrappers = Context.click()
    for wrapper in wrappers.values():
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

        # context overrides
        kwargs["ctx"] = ctx = Context().populate()
        for key in wrappers:
            value = kwargs.pop(key)
            #value = kwargs.pop(key.replace("_", "-"))
            setattr(ctx, key, value)
        return fn(*args, **kwargs)
    return _fn

# host:
#    config.guess aarch64-apple-darwin20.6.0
#    sysconfig.get_platform() 'macosx-11.0-arm64'
# target: 

@click.group()
def main():
    pass


@main.command()
@click.option("--compact", is_flag=True, help="Produce a compact list suitable for scripting")
@common_options
def recipes(ctx, compact):
    "List all the available recipes"
    rm = RecipeManager(ctx)
    if compact:
        print(" ".join(sorted(str(r[0]) for r in rm)))
    else:
        for recipe in sorted(rm, key=lambda r: r.name.upper()):
            if not recipe.version:
                logger.debug("skipping %s without version", recipe.name)
                continue
            print(f"{recipe.name:<12} {recipe.version:<8}")


@main.command(name="build_info")
@common_options
def build_info():
    from pprint import pformat
    ctx = Context()
    ctx.populate()
    print("Build Context")
    print("-------------")
    for attr in sorted(set(dir(ctx)) - {"populate"}):
        if attr.startswith("_") or attr == "archs":
            continue
        if not callable(attr):
            value = getattr(ctx, attr)
            print(f"{attr}: {pformat(value)}")
    for arch in ctx.archs:
        ul = '-' * (len(str(arch))+6)
        print("\narch: {}\n{}".format(str(arch), ul))
        for attr in dir(arch):
            if not attr.startswith("_"):
                if not callable(attr) and attr not in ['arch', 'ctx', 'get_env']:
                    print("{}: {}".format(attr, pformat(getattr(arch, attr))))
        env = arch.get_env()
        print("env ({}): {}".format(arch, pformat(env)))


@main.command()
@common_options
def status():
    ctx = Context()
    rm = RecipeManager()
    for recipe in sorted(rm.list_recipes()):
        key = f"{recipe}.build_all"
        keytime = f"{recipe}.build_all.at"
        if key in ctx.state:
            status = "Build OK (built at {})".format(ctx.state[keytime])
        else:
            status = "Not built"
        print("{:<12} - {}".format(
                recipe, status))


@main.command()
@common_options
def build(ctx):
    print(ctx.num_cores)


if __name__ == "__main__":
    main()
