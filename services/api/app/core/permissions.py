"""Tool authorization: per-user enablement, integration connection and approval requirements.
Text, voice, automations and approvals all use this same evaluation."""

from __future__ import annotations

from dataclasses import dataclass

from app.assistant.tools import ToolSpec
from app.database import models as m


@dataclass(frozen=True)
class Decision:
    allowed: bool
    needs_approval: bool = False
    reason: str | None = None
    code: str | None = None


def evaluate(
    spec: ToolSpec,
    *,
    channel: str,
    permissions: dict[str, m.ToolPermission],
    connected: set[str],
    preferences: dict[str, object] | None = None,
) -> Decision:
    if channel not in spec.channels:
        return Decision(False, reason=f"{spec.name} is not available in {channel} mode", code="channel_denied")
    perm = permissions.get(spec.name)
    if perm is not None and not perm.enabled:
        return Decision(
            False, reason=f"You disabled the '{spec.name}' tool in Settings > Permissions", code="tool_disabled"
        )
    if spec.category == "memory" and preferences is not None and not preferences.get("memory_enabled", True):
        return Decision(False, reason="Memory is turned off in your privacy settings", code="memory_disabled")
    if spec.integration and spec.integration not in connected:
        return Decision(
            False,
            reason=f"{spec.integration.title()} is not connected. Connect it in Integrations.",
            code=f"{spec.integration}_not_connected",
        )
    if channel == "approval":
        return Decision(True)  # the approval itself is the user's authorization
    if spec.approval == "always":
        return Decision(True, needs_approval=True)
    if spec.approval == "configurable":
        required = perm.requires_approval if perm is not None else spec.risk != "read"
        if channel == "automation" and spec.risk != "read":
            required = True
        return Decision(True, needs_approval=required)
    if channel == "automation" and spec.risk == "sensitive":
        return Decision(True, needs_approval=True)
    return Decision(True)
