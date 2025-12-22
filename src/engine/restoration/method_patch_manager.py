from types import MethodType
from typing import Any, Callable, Generic, TypeVar, Type


class MethodPatchManager():
    """
    Patch class methods OR instance methods.
    """

    def __init__(
        self,
        target,
        method_map: dict[str, tuple[Callable[..., Any], Callable[..., Any]]],
    ) -> None:
        self.target = target
        self.method_map = method_map
        self._instance_originals = {}

    def patch(self, name=None) -> None:
        """
        Patch a single method or all methods.
        """
        if name:
            self._patch_one(name)
        else:
            for n in self.method_map.keys():
                self._patch_one(n)

    def restore(self, name=None) -> None:
        """
        Restore a single method or all methods.
        """
        if name:
            self._restore_one(name)
        else:
            for n in self.method_map.keys():
                self._restore_one(n)

    def _patch_one(self, name) -> None:
        orig, patched = self.method_map[name]

        if not isinstance(self.target, type):
            # Save original only once
            if name not in self._instance_originals:
                self._instance_originals[name] = getattr(self.target, name)

            setattr(self.target, name, MethodType(patched, self.target))
            return

        current_attr = getattr(self.target, name)
        is_classmethod = isinstance(current_attr, classmethod)

        if is_classmethod:
            setattr(self.target, name, classmethod(patched))
        else:
            setattr(self.target, name, patched)

    def _restore_one(self, name) -> None:
        orig, _ = self.method_map[name]

        if not isinstance(self.target, type):
            if name in self._instance_originals:
                setattr(self.target, name, self._instance_originals[name])
            return

        setattr(self.target, name, orig)
