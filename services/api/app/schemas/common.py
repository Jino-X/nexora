from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    items: list[T]
    has_more: bool
    next_offset: int | None = None

    @classmethod
    def of(cls, items: list[T], has_more: bool, offset: int, limit: int) -> Page[T]:
        return cls(items=items, has_more=has_more, next_offset=offset + limit if has_more else None)


class OkResponse(BaseModel):
    ok: bool = True
    detail: str | None = None
