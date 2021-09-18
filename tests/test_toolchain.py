import json
import pathlib
from kivy_ios import toolchain2

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
    

def test_recipemanager():
    ctx = toolchain2.Context()
    rm = toolchain2.RecipeManager(ctx)
    assert rm.get_recipe("numpy")
