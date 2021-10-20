import sys
import logging

import pytest

import kivy_ios.sh

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="does not run on windows")


def test_logging(caplog):
    sh = kivy_ios.sh.Sh("my-log-name", flag=kivy_ios.sh.Flag.STRIP)
    
    with caplog.at_level(logging.INFO, logger="my-log-name"):
        assert not sh.ls("file-not-present")
        pytest.raises(RuntimeError, sh.ls, "file-not-present", sh.flag | sh.flag.ABORT)
        assert not caplog.record_tuples

    
    with caplog.at_level(logging.DEBUG, logger="my-log-name"):
        assert __file__ == sh.ls(__file__)
        assert [('my-log-name', logging.DEBUG, f"running (with flag=Flag.STRIP): ['ls', '{__file__}']")] == caplog.record_tuples
        caplog.clear()

        assert not sh.ls("file-not-present")
        assert [('my-log-name', logging.DEBUG, f"running (with flag=Flag.STRIP): ['ls', 'file-not-present']")] == caplog.record_tuples
        caplog.clear()
        

def test_flags():
    sh = kivy_ios.sh.Sh("my-log-name", flag=kivy_ios.sh.Flag.STRIP)
    assert not sh.ls("file-not-present")

    # we can abort flipping the ABORT flag
    pytest.raises(RuntimeError, sh.ls, "file-not-present", sh.flag.ABORT)
    

def test_shprint(caplog):
    sh = kivy_ios.sh.Sh("my-log-name", flag=kivy_ios.sh.Flag.STRIP | kivy_ios.sh.Flag.SHPRINT)
    with caplog.at_level(logging.DEBUG, logger="my-log-name"):
        assert __file__ == sh.ls(__file__)
        assert ('my-log-name', logging.DEBUG, 'err> ') in caplog.record_tuples
        assert ('my-log-name', logging.DEBUG, f'out> {__file__}') in caplog.record_tuples
        caplog.clear()


def test_fullcmd(caplog):
    "using an executable full path"
    sh = kivy_ios.sh.Sh("my-log-name", flag=kivy_ios.sh.Flag.STRIP)
    ls = sh.which("ls")
    assert __file__ == getattr(sh, ls)(__file__)
