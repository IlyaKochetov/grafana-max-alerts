from typing import Any

from pydantic import BaseModel, Field

from app.config import Settings
from app.exceptions import RoutingError
from app.schemas.normalized import AlertGroup


class RouteConfig(BaseModel):
    name: str
    match: dict[str, str] = Field(default_factory=dict)
    chat_id: int
    notify: bool = True
    template: str = "group"


class DefaultRouteConfig(BaseModel):
    chat_id: int
    notify: bool = True
    template: str = "group"


class ResolvedRoute(BaseModel):
    name: str
    chat_id: int
    notify: bool = True
    template: str = "group"


class RouterConfig(BaseModel):
    routes: list[RouteConfig] = Field(default_factory=list)
    default_route: DefaultRouteConfig | None = None

    @classmethod
    def from_settings(cls, settings: Settings, yaml_config: dict[str, Any]) -> "RouterConfig":
        routes = [RouteConfig.model_validate(item) for item in yaml_config.get("routes", [])]
        default_raw = yaml_config.get("default_route")
        default_route = None
        if isinstance(default_raw, dict):
            default_route = DefaultRouteConfig.model_validate(default_raw)
        if default_route is None and settings.max_default_chat_id is not None:
            default_route = DefaultRouteConfig(chat_id=settings.max_default_chat_id)
        return cls(routes=routes, default_route=default_route)


class AlertRouter:
    def __init__(self, config: RouterConfig) -> None:
        self.routes = config.routes
        self.default_route = config.default_route

    def resolve_routes(self, group: AlertGroup) -> list[ResolvedRoute]:
        resolved: list[ResolvedRoute] = []
        seen_chat_ids: set[int] = set()

        for route in self.routes:
            if self._route_matches(route, group) and route.chat_id not in seen_chat_ids:
                resolved.append(
                    ResolvedRoute(
                        name=route.name,
                        chat_id=route.chat_id,
                        notify=route.notify,
                        template=route.template,
                    )
                )
                seen_chat_ids.add(route.chat_id)

        if resolved:
            return resolved

        if self.default_route is None:
            raise RoutingError("No route matched and default route is not configured")

        return [
            ResolvedRoute(
                name="default",
                chat_id=self.default_route.chat_id,
                notify=self.default_route.notify,
                template=self.default_route.template,
            )
        ]

    @staticmethod
    def _route_matches(route: RouteConfig, group: AlertGroup) -> bool:
        if not route.match:
            return True
        for alert in group.alerts:
            labels = {**group.common_labels, **alert.labels}
            if all(labels.get(key) == value for key, value in route.match.items()):
                return True
        return False
