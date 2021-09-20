import json
import pytest
import pathlib
import dataclasses as dc
from kivy_ios import toolchain2


def test_unravel():
    data = {
        "prefix": "/a/b/c",
        "flags": [
            "/c/d/e",
            "{prefix}/wow",
            "/A/{flags1}",
        ],
        "flags1": "/x/y",
        "k": 1,
    }
    out = toolchain2.unravel(data)
    assert out == {
        "prefix": "/a/b/c",
        "flags": [
            "/c/d/e",
            "/a/b/c/wow",
            "/A//x/y",
        ],
        "flags1": "/x/y",
        "k": 1,
    }

def test_configguess():
    assert toolchain2.config_guess() == "aarch64-apple-*"
    assert toolchain2.config_guess() != "arm-apple-*"


def test_loadr():
    assert not toolchain2.loadr("hello")
    assert toolchain2.loadr("kivy_ios.recipes.openssl")


def test_loadr_with_path():
    path = pathlib.Path(toolchain2.__file__).parent / "recipes/numpy"
    assert path.exists() and path.is_dir()

    assert toolchain2.loadr("abc", path / "__init__.py")


def test_json_store(tmp_path):
    db = tmp_path / "data.db"
    js = toolchain2.JsonStore(db)
    assert not db.exists()

    js["x"] = 1
    assert db.exists()
    assert { "x" : 1 } == json.loads(db.read_bytes())

    js["x"] = 2
    assert { "x" : 2 } == json.loads(db.read_bytes())

    js["y"] = 3
    assert { "x" : 2, "y" : 3 } == json.loads(db.read_bytes())

    del js["x"]
    assert { "y" : 3 } == json.loads(db.read_bytes())


def test_sh():
    sh = toolchain2.Sh()
    assert sh.which("python")
    

def test_flags():
    f = toolchain2.IFlag("/abc/def")
    assert str(f) == "-I/abc/def"

    f = toolchain2.LFlag("/abc/def")
    assert str(f) == "-L/abc/def"

    f = toolchain2.DFlag("A")
    assert str(f) == "-DA"

    f = toolchain2.DFlag("A", 1)
    assert str(f) == "-DA=1"

    f = toolchain2.lFlag("m")
    assert str(f) == "-lm"


def test_arch():
    arch = toolchain2.Arch64Simulator()
    tag = "/Applications/Xcode.app/Contents/Developer/Platforms/iPhoneSimulator.platform/Developer/SDKs/iPhoneSimulator"
    assert str(arch.sysroot)[:len(tag)] == tag


def test_context():
    from attr.exceptions import FrozenInstanceError
    ctx = toolchain2.Context()
    pytest.raises(AttributeError, setattr, ctx, "hello", "world")


def test_recipemanager():
    ctx = toolchain2.Context()
    rm = toolchain2.RecipeManager(ctx)
    assert rm.get_recipe("numpy")


def test_arch_env():
    arch = toolchain2.Arch64Simulator()
    print("xxx", arch.sysroot)
    assert not arch.includes

    arch.includes = [
        str(path).format(**dc.asdict(arch))
        for path in [
            "/a/b/c/{sdk}",
            "/a/b/c/{sdk}/{triple}",
            "/a/b/c/{sdk}/{triple}/{arch}",
        ]
    ]
    assert arch.includes == [
        "/a/b/c/iphonesimulator",
        "/a/b/c/iphonesimulator/x86_64-apple-darwin13",
        "/a/b/c/iphonesimulator/x86_64-apple-darwin13/x86_64",
    ]
