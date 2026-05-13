from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from app.schemas.normalized import AlertEvent, AlertGroup

TRUNCATED_SUFFIX = "\n\n... truncated"
MSK = ZoneInfo("Europe/Moscow")


class MessageFormatter:
    def __init__(self, templates_dir: Path | None = None) -> None:
        directory = templates_dir or Path(__file__).resolve().parent.parent / "templates"
        self.environment = Environment(
            loader=FileSystemLoader(directory),
            autoescape=select_autoescape(default=False),
            undefined=StrictUndefined,
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self.environment.filters["datetime_msk"] = format_datetime_msk
        self.environment.filters["duration"] = format_duration

    def format_group(self, group: AlertGroup, template_name: str = "group") -> str:
        if len(group.alerts) == 1 and template_name == "group":
            return self.format_single(group.alerts[0])
        template = self.environment.get_template(f"{template_name}.md.j2")
        return template.render(group=group).strip()

    def format_single(self, alert: AlertEvent) -> str:
        template = self.environment.get_template(f"{alert.status}.md.j2")
        return template.render(alert=alert).strip()


def truncate_message(text: str, max_length: int) -> str:
    if max_length <= len(TRUNCATED_SUFFIX):
        return TRUNCATED_SUFFIX[-max_length:]
    if len(text) <= max_length:
        return text
    return text[: max_length - len(TRUNCATED_SUFFIX)].rstrip() + TRUNCATED_SUFFIX


def format_datetime_msk(value: datetime | None) -> str:
    if value is None:
        return "-"
    return value.astimezone(MSK).strftime("%Y-%m-%d %H:%M MSK")


def format_duration(start: datetime | None, end: datetime | None) -> str:
    if start is None or end is None:
        return "-"
    seconds = max(int((end - start).total_seconds()), 0)
    minutes, remaining_seconds = divmod(seconds, 60)
    hours, remaining_minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {remaining_minutes}m {remaining_seconds}s"
    if minutes:
        return f"{minutes}m {remaining_seconds}s"
    return f"{remaining_seconds}s"
