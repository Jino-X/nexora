"""WhatsApp Business (Cloud API) tool. Every send requires explicit approval."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.assistant.tools import ToolContext, ToolRegistry, ToolResult, ToolSpec


class WhatsAppArgs(BaseModel):
    to: str = Field(max_length=20, description="Recipient phone number in international format, e.g. +919876543210")
    message: str = Field(min_length=1, max_length=4096)


async def whatsapp_send_message(ctx: ToolContext, args: WhatsAppArgs) -> ToolResult:
    client = await ctx.services.whatsapp.client_for(ctx.session, ctx.user_id)
    result = await client.send_text(args.to, args.message)
    return ToolResult(
        ok=True,
        message=f"WhatsApp message sent to +{result.to}.",
        data=result.model_dump(),
        card={"type": "whatsapp_sent", "to": result.to},
    )


def _summary(args: WhatsAppArgs) -> str:
    text = args.message.replace("\n", " ")
    return f"Send WhatsApp message to {args.to}: {text[:200]}{'...' if len(text) > 200 else ''}"


def register(registry: ToolRegistry) -> None:
    registry.register(
        ToolSpec(
            name="whatsapp_send_message",
            category="whatsapp",
            integration="whatsapp",
            args_model=WhatsAppArgs,
            handler=whatsapp_send_message,
            risk="sensitive",
            approval="always",
            summarize=_summary,
            description="Send a WhatsApp message from the user's connected WhatsApp Business number. Requires explicit "
            "approval. Only works within 24h of the recipient's last message unless a template is used.",
        )
    )
