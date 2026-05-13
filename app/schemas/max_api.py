from typing import Any, Literal

from pydantic import BaseModel, Field

TextFormat = Literal["markdown", "html"]


class SendMessageRequest(BaseModel):
    text: str
    format: TextFormat = "markdown"
    notify: bool = True
    disable_link_preview: bool = False


class SendMessageResult(BaseModel):
    message_id: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)
