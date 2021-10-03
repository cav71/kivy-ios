from kivy_ios.toolchain3 import util

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
    out = util.unravel(data)
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


def test_unravel1():
    assert util.unravel({ "a": "hello", "b": "{a} world"}) == { "a": "hello", "b": "hello world"}
