from app.schemas.normalized import AlertEvent, AlertGroup
from app.services.router import AlertRouter, DefaultRouteConfig, RouteConfig, RouterConfig


def make_group() -> AlertGroup:
    return AlertGroup(
        status="firing",
        group_key="group",
        common_labels={"service": "samolet"},
        alerts=[
            AlertEvent(
                status="firing",
                alertname="High CPU usage",
                severity="critical",
                service="samolet",
                environment="prod",
                fingerprint="abc123",
                labels={"severity": "critical", "env": "prod"},
            )
        ],
    )


def test_default_route_when_no_match() -> None:
    router = AlertRouter(RouterConfig(default_route=DefaultRouteConfig(chat_id=1)))

    routes = router.resolve_routes(make_group())

    assert routes[0].chat_id == 1


def test_matches_by_service_severity_and_env() -> None:
    router = AlertRouter(
        RouterConfig(
            routes=[
                RouteConfig(name="service", match={"service": "samolet"}, chat_id=1),
                RouteConfig(name="severity", match={"severity": "critical"}, chat_id=2),
                RouteConfig(name="env", match={"env": "prod"}, chat_id=3),
            ]
        )
    )

    routes = router.resolve_routes(make_group())

    assert [route.chat_id for route in routes] == [1, 2, 3]


def test_deduplicates_same_chat_id() -> None:
    router = AlertRouter(
        RouterConfig(
            routes=[
                RouteConfig(name="a", match={"service": "samolet"}, chat_id=1),
                RouteConfig(name="b", match={"severity": "critical"}, chat_id=1),
            ]
        )
    )

    routes = router.resolve_routes(make_group())

    assert [route.chat_id for route in routes] == [1]
