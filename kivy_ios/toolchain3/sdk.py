import logging
from typing import Optional, Union, List
import attr

from .context import GnuFlags, IFlag, DFlag, LFlag, lFlag
from .util import Sh


log = logging.getLogger(__name__)
sh = Sh(log=__name__)


@attr.s(slots=True, auto_attribs=True)
class Env:
    cc : str = ""  
    cxx : str = ""
    ar : str = ""
    ld : str = ""
    sysroot : str = ""

    gnuflags : GnuFlags = GnuFlags()


def load_macos_sdk_env(sdk, arch):
    name = sdk["canonicalName"]
    env = Env(
        cc=sh.xcrun("-find", "-sdk", name, "clang"),
        cxx=sh.xcrun("-find", "-sdk", name, "clang++"),
        ar=sh.xcrun("-find", "-sdk", name, "ar"),
        ld=sh.xcrun("-find", "-sdk", name, "ld"),
        sysroot=sh.xcrun("--sdk", name, "--show-sdk-path")
    )

    subs = [ "--sysroot", f"{env.sysroot}", ]

    platform = sdk["platform"]
    if (platform, arch) == ("iphoneos", "arm64"):
        env.gnuflags.host = "aarch64-apple-darwin13"
        subs.append("-miphoneos-version-min=9.0")
    else:
        raise RuntimeError(f"unsupported paltform, arch ({platform}, {arch})")

    if platform == 'iphoneos':
        subs.append("-fembed-bitcode")

    env.gnuflags.cflags.extend(subs)
    env.gnuflags.cxxflags.extend(subs)

    
    return env


def macos_sdks():
    sdks = sh.xcodebuild("-sdk", "-version", "-json", sh.flag.JSON)
    breakpoint()
    return {
        sdk["canonicalName"]: sdk
        for sdk in sdks
    }


def sdks(plat: Optional[str]=None):
    # xcodebuild -sdk -version -json
    plat = plat or "macos"
    assert plat in { "macos" }, f"cannot handle platform {plat}"
    return macos_sdks()    

