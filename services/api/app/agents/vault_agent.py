"""Vault tool: metadata only. Secret values are never readable by the assistant. The user reveals
them in the Vault UI, which is a separate, audited endpoint."""

from __future__ import annotations

from pydantic import BaseModel, Field
from sqlalchemy import select

from app.assistant.tools import ToolContext, ToolRegistry, ToolResult, ToolSpec
from app.database import models as m


class VaultListArgs(BaseModel):
    query: str | None = Field(None, max_length=100, description="Optional name filter")


async def vault_list_items(ctx: ToolContext, args: VaultListArgs) -> ToolResult:
    stmt = select(m.VaultItem.id, m.VaultItem.name, m.VaultItem.kind, m.VaultItem.description).where(
        m.VaultItem.user_id == ctx.user_id
    )
    if args.query:
        stmt = stmt.where(m.VaultItem.name.ilike(f"%{args.query}%"))
    rows = (await ctx.session.execute(stmt.order_by(m.VaultItem.name).limit(25))).all()
    items = [{"id": str(r.id), "name": r.name, "kind": r.kind, "description": r.description} for r in rows]
    msg = (
        f"You have {len(items)} matching vault item(s). Open the Vault to reveal a value."
        if items
        else "No matching vault items."
    )
    return ToolResult(
        ok=True,
        message=msg,
        data={
            "items": [{"name": i["name"], "kind": i["kind"]} for i in items],
            "note": "Secret values are not available to the assistant.",
        },
        card={"type": "vault_items", "items": items},
    )


def register(registry: ToolRegistry) -> None:
    registry.register(
        ToolSpec(
            name="vault_list_items",
            category="vault",
            args_model=VaultListArgs,
            handler=vault_list_items,
            description="List the names of items in the user's secure vault. You can NEVER see secret values; point "
            "the user to the Vault page to reveal them.",
        )
    )
