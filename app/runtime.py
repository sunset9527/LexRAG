"""Request-independent services created during the FastAPI application lifespan."""

from __future__ import annotations


class RuntimeComponentUnavailable(RuntimeError):
    """Raised when a route requests a component that is not ready."""

    code = "RUNTIME_COMPONENT_UNAVAILABLE"

    def __init__(self, component: str) -> None:
        self.component = component
        super().__init__(f"Runtime component is unavailable: {component}")


class RuntimeContainer:
    """Small typed seam around process-wide, request-independent services.

    Components are intentionally registered only at startup. Request-specific
    data such as a user, API key, or query state must not be stored here.
    """

    def __init__(self, **components: object) -> None:
        self._components = dict(components)

    def require(self, component: str) -> object:
        value = self._components.get(component)
        if value is None:
            raise RuntimeComponentUnavailable(component)
        return value

    def get(self, component: str) -> object | None:
        return self._components.get(component)

    def register(self, component: str, value: object) -> None:
        """Register a startup-created component during the migration period."""

        self._components[component] = value

    def replace(self, **components: object) -> None:
        """Atomically replace the startup component set while keeping references valid."""

        self._components.clear()
        self._components.update(components)

    def __getitem__(self, component: str) -> object:
        return self.require(component)

    def __setitem__(self, component: str, value: object) -> None:
        self.register(component, value)
