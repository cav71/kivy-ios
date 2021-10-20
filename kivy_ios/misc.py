import functools
import logging


class Tracer(type):
    def __new__(cls, name, bases, dct):
        klass = super().__new__(cls, name, bases, dct)
        for prop, value in klass.props.items():
            if not hasattr(klass, prop):
                setattr(klass, prop, value)
        for m in dir(klass):
            if m.startswith("_") and not m == "__init__":
                continue
            def fn(f):
                @functools.wraps(f)
                def _fn(self, *args, **kwargs):
                    logging.debug("executing %s.%s", f.__class__.__name__, f.__name__)
                    #breakpoint()
                    return f(self, *args, **kwargs)
                return _fn
            if callable(getattr(klass, m)):
                setattr(klass, m, fn(getattr(klass, m)))
        return klass
