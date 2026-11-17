"""Gmail tools. Reading is allowed once Gmail is connected. Creating drafts and sending need the
user's explicit approval."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.assistant.tools import ToolContext, ToolRegistry, ToolResult, ToolSpec


class SearchArgs(BaseModel):
    query: str = Field(max_length=300, description="Gmail search query, e.g. 'from:bank newer_than:7d'")
    max_results: int = Field(8, ge=1, le=20)


class UnreadArgs(BaseModel):
    max_results: int = Field(10, ge=1, le=20)


class ReadArgs(BaseModel):
    message_id: str = Field(min_length=6, max_length=64)


class DraftArgs(BaseModel):
    to: str = Field(max_length=320, description="Recipient email address")
    subject: str = Field(max_length=250)
    body: str = Field(max_length=20000)
    cc: str | None = Field(None, max_length=1000)


def _emails_result(emails: list, label: str) -> ToolResult:
    data = [
        {"id": e.id, "from": e.from_, "subject": e.subject, "date": e.date, "snippet": e.snippet, "unread": e.unread}
        for e in emails
    ]
    msg = f"{len(emails)} {label}." if emails else f"No {label}."
    return ToolResult(
        ok=True,
        message=msg,
        data=data,
        card={"type": "emails", "items": [e.model_dump(by_alias=False) for e in emails]},
    )


async def gmail_unread(ctx: ToolContext, args: UnreadArgs) -> ToolResult:
    client = await ctx.services.gmail.client_for(ctx.session, ctx.user_id)
    return _emails_result(await client.list_messages("is:unread in:inbox", args.max_results), "unread emails")


async def gmail_search(ctx: ToolContext, args: SearchArgs) -> ToolResult:
    client = await ctx.services.gmail.client_for(ctx.session, ctx.user_id)
    return _emails_result(await client.list_messages(args.query, args.max_results), "matching emails")


async def gmail_read(ctx: ToolContext, args: ReadArgs) -> ToolResult:
    client = await ctx.services.gmail.client_for(ctx.session, ctx.user_id)
    email = await client.get_message(args.message_id)
    data = {
        "from": email.from_,
        "to": email.to,
        "subject": email.subject,
        "date": email.date,
        "body": (email.body_text or "")[:4000],
    }
    return ToolResult(
        ok=True,
        message=f"Email from {email.from_}: {email.subject}",
        data=data,
        card={"type": "email", "item": email.model_dump()},
    )


async def gmail_create_draft(ctx: ToolContext, args: DraftArgs) -> ToolResult:
    client = await ctx.services.gmail.client_for(ctx.session, ctx.user_id)
    draft = await client.create_draft(args.to, args.subject, args.body, args.cc)
    return ToolResult(
        ok=True,
        message=f"Draft to {args.to} saved in Gmail.",
        data=draft.model_dump(),
        card={"type": "email_draft", "draft": draft.model_dump()},
    )


async def gmail_send_email(ctx: ToolContext, args: DraftArgs) -> ToolResult:
    client = await ctx.services.gmail.client_for(ctx.session, ctx.user_id)
    draft = await client.create_draft(args.to, args.subject, args.body, args.cc)
    sent = await client.send_draft(draft.draft_id)
    return ToolResult(
        ok=True,
        message=f"Email sent to {args.to}.",
        data={"to": args.to, **sent},
        card={"type": "email_sent", "to": args.to, "subject": args.subject},
    )


def _summary(verb: str):
    def summarize(args: DraftArgs) -> str:
        preview = args.body.strip().replace("\n", " ")
        preview = preview[:160] + ("..." if len(preview) > 160 else "")
        return f'{verb} email to {args.to} - "{args.subject}": {preview}'

    return summarize


def register(registry: ToolRegistry) -> None:
    registry.register(
        ToolSpec(
            name="gmail_unread",
            category="gmail",
            integration="gmail",
            args_model=UnreadArgs,
            handler=gmail_unread,
            description="List the user's unread inbox emails (sender, subject, snippet). Use to summarize unread mail.",
        )
    )
    registry.register(
        ToolSpec(
            name="gmail_search",
            category="gmail",
            integration="gmail",
            args_model=SearchArgs,
            handler=gmail_search,
            description="Search the user's Gmail with Gmail search syntax.",
        )
    )
    registry.register(
        ToolSpec(
            name="gmail_read",
            category="gmail",
            integration="gmail",
            args_model=ReadArgs,
            handler=gmail_read,
            description="Read the full text of one email by id (from gmail_unread or gmail_search).",
        )
    )
    registry.register(
        ToolSpec(
            name="gmail_create_draft",
            category="gmail",
            integration="gmail",
            args_model=DraftArgs,
            handler=gmail_create_draft,
            risk="write",
            approval="configurable",
            summarize=_summary("Save draft"),
            description="Create a Gmail draft (not sent). The user approves it in the app first.",
        )
    )
    registry.register(
        ToolSpec(
            name="gmail_send_email",
            category="gmail",
            integration="gmail",
            args_model=DraftArgs,
            handler=gmail_send_email,
            risk="sensitive",
            approval="always",
            summarize=_summary("Send"),
            description="Send an email. Always requires the user's explicit approval in the app before sending.",
        )
    )
