
from typing import runtime_checkable, Protocol

@runtime_checkable
class P(Protocol):
    @property
    def bar(self): pass

class Foo:
    @property
    def bar(self):
        # Test that this is never reached
        raise RuntimeError

assert isinstance(Foo(), P)