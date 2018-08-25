import typing


class Category:

    def __init__(self, name: str):
        self.name = name


class CategoryScope:

    def __init__(self, category: Category):
        self.category = category
        self.count = 0

    def add(self, amount):
        self.count += amount


class Scope:

    def __init__(self, name: str, *categories: Category):
        self.name = name
        self.categories = dict([
            (category.name, CategoryScope(category))
            for category in categories
        ])

    def add(self, name, amount):
        self.categories[name].add(amount)


class Stack:

    def __init__(self, *categories: Category):
        self.stack = typing.cast(typing.List[Scope], [])
        self.categories = categories

    def push(self, name):
        def scope_constructor():
            return Scope(name, *self.categories)

        return StackScopeGuard(self, scope_constructor)

    def add(self, name, amount):
        for level in self.stack:
            level.add(name, amount)

    def _pop(self):
        return self.stack.pop()


class StackScopeGuard:

    def __init__(self, stack: Stack, scope_constructor: typing.Callable[[], Scope]):
        self._stack = stack
        self._scope_constructor = scope_constructor

    def __enter__(self):
        scope = self._scope_constructor()
        self._stack.stack.append(scope)
        return scope

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._stack._pop()

