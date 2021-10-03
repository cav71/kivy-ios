from kivy_ios.toolchain3 import flags


def test_flags():
    f = flags.IFlag("/abc/def")
    assert str(f) == "-I/abc/def"

    f = flags.LFlag("/abc/def")
    assert str(f) == "-L/abc/def"

    f = flags.DFlag("A")
    assert str(f) == "-DA"

    f = flags.DFlag("A", 1)
    assert str(f) == "-DA=1"

    f = flags.lFlag("m")
    assert str(f) == "-lm"


