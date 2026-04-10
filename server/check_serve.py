from trame.app import get_server
s = get_server()
import inspect
print(inspect.signature(s.serve) if callable(s.serve) else type(s.serve))
print(repr(s.serve))
print()
print(repr(s._www))
