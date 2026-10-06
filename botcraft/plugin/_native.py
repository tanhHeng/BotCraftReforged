"""Local MCDR 2.14.4 function bindings; never mutate native classes or globals."""
from typing import Any, Callable, Mapping, TypeVar
from types import CellType

_NativeFunction = TypeVar("_NativeFunction", bound=Callable[..., Any])
from types import CodeType, FunctionType


def _runtime_names(code: CodeType) -> CodeType:
    constants = tuple(_runtime_names(value) if isinstance(value, CodeType) else value for value in code.co_consts)
    names = tuple('runtime' if name == 'mcdr_server' else name for name in code.co_names)
    return code.replace(co_names=names, co_consts=constants)


def bind_native(method: _NativeFunction, *, runtime: bool = False, globals: Mapping[str, Any] | None = None, owner: type | None = None) -> _NativeFunction:
    """Bind a native Python function to an isolated BotCraft namespace.
    
    :param method: Native function whose code and annotations are preserved.
    :param runtime: Rewrite native host attribute references to runtime.
    :param globals: Namespace replacements needed by the adapter.
    :param owner: Class used to replace a native super() closure.
    :return: Isolated function retaining the native signature and annotations.
    """
    namespace = dict(method.__globals__)
    if globals:
        namespace.update(globals)
    code = _runtime_names(method.__code__) if runtime else method.__code__
    closure = method.__closure__
    if owner is not None and closure:
        def cell(value: object) -> CellType:
            """Create a closure cell for a replacement owner.
            
            :param value: Value captured by the closure cell.
            :return: Cell containing the supplied value.
            """
            return (lambda: value).__closure__[0]
        closure = tuple(cell(owner) if name == '__class__' else value for name, value in zip(method.__code__.co_freevars, closure))
    result = FunctionType(code, namespace, method.__name__, method.__defaults__, closure)
    result.__kwdefaults__ = method.__kwdefaults__
    result.__annotations__ = method.__annotations__
    result.__doc__ = method.__doc__
    result.__native_origin__ = method
    return result
