"""Personal memory: user-controlled, isolated per user, semantically searchable.

Policy:
* Only explicit saves (UI, or the assistant's `memory_save` tool when the user asks it to
  remember something) create memories. Conversation-derived memories need
  `memory_auto_extract=true`.
* Text that looks like a credential is refused and redirected to the vault.
* Retention: `expires_at` per memory. The automation worker purges expired rows.
"""

from __future__ import annotations

import re
import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationFailedError
from app.database import models as m
from app.database import repositories as repo
from app.database.base import utcnow
from app.memory.embeddings import ResilientEmbeddings, cosine

MEMORY_KINDS = ("profile", "preference", "fact", "project", "conversation_summary", "note")

SECRET_PATTERNS = [
    re.compile(r"\b(password|passcode|passwd|pin|otp|cvv)\b\s*(is|:|=)", re.IGNORECASE),
    re.compile(r"\b(sk|pk|rk)-[A-Za-z0-9_-]{16,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b"),
    re.compile(r"\b(?:\d[ -]?){13,19}\b"),  # card-like numbers
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
]


def looks_like_secret(text: str) -> bool:
    return any(p.search(text) for p in SECRET_PATTERNS)


class MemoryService:
    def __init__(self, embeddings: ResilientEmbeddings, use_pgvector: bool) -> None:
        self.embeddings = embeddings
        self.use_pgvector = use_pgvector

    async def create(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        content: str,
        *,
        kind: str = "fact",
        source: str = "user",
        importance: int = 3,
        pinned: bool = False,
        source_conversation_id: uuid.UUID | None = None,
        retention_days: int | None = None,
    ) -> m.Memory:
        content = content.strip()
        if not content:
            raise ValidationFailedError("Memory content is empty")
        if len(content) > 4000:
            raise ValidationFailedError("Memory is too long (max 4000 characters)")
        if kind not in MEMORY_KINDS:
            raise ValidationFailedError(f"Unknown memory kind '{kind}'")
        if looks_like_secret(content):
            raise ValidationFailedError(
                "This looks like a password or secret. Store it in the secure vault instead of memory.",
                code="secret_in_memory",
            )
        vectors = await self.embeddings.try_embed([content])
        memory = m.Memory(
            user_id=user_id,
            content=content,
            kind=kind,
            source=source,
            importance=max(1, min(importance, 5)),
            pinned=pinned,
            source_conversation_id=source_conversation_id,
            embedding=vectors[0] if vectors else None,
            embedding_model=self.embeddings.model_id if vectors else None,
            expires_at=utcnow() + timedelta(days=retention_days) if retention_days else None,
        )
        session.add(memory)
        await session.flush()
        return memory

    async def update(
        self, session: AsyncSession, user_id: uuid.UUID, memory_id: uuid.UUID, changes: dict[str, Any]
    ) -> m.Memory:
        memory = await repo.get_owned(session, m.Memory, user_id, memory_id, label="Memory")
        if "content" in changes and changes["content"] is not None:
            content = str(changes["content"]).strip()
            if looks_like_secret(content):
                raise ValidationFailedError("This looks like a secret. Use the vault instead.", code="secret_in_memory")
            memory.content = content
            vectors = await self.embeddings.try_embed([content])
            memory.embedding = vectors[0] if vectors else None
            memory.embedding_model = self.embeddings.model_id if vectors else None
        for key in ("kind", "importance", "pinned", "expires_at"):
            if key in changes and changes[key] is not None:
                setattr(memory, key, changes[key])
        await session.flush()
        return memory

    def _base(self, user_id: uuid.UUID) -> Select[Any]:
        now = utcnow()
        return select(m.Memory).where(
            m.Memory.user_id == user_id, or_(m.Memory.expires_at.is_(None), m.Memory.expires_at > now)
        )

    async def search(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        query: str,
        *,
        limit: int = 5,
        min_score: float = 0.2,
        touch: bool = False,
    ) -> list[tuple[m.Memory, float]]:
        query = query.strip()
        if not query:
            return []
        vectors = await self.embeddings.try_embed([query])
        results: list[tuple[m.Memory, float]] = []
        if vectors:
            qvec = vectors[0]
            stmt = self._base(user_id).where(m.Memory.embedding_model == self.embeddings.model_id)
            if self.use_pgvector:
                distance = m.Memory.embedding.cosine_distance(qvec)  # type: ignore[union-attr]
                rows = (
                    await session.execute(
                        select(m.Memory, distance.label("d"))
                        .where(stmt.whereclause)  # type: ignore[arg-type]
                        .order_by(distance)
                        .limit(limit)
                    )
                ).all()
                results = [(row[0], 1.0 - float(row[1])) for row in rows]
            else:
                rows = (await session.execute(stmt.limit(5000))).scalars().all()
                scored = [(mem, cosine(qvec, mem.embedding or [])) for mem in rows]
                results = sorted(scored, key=lambda s: s[1], reverse=True)[:limit]
            results = [(mem, score) for mem, score in results if score >= min_score]
        if len(results) < limit:
            # Keyword fallback: memories without a compatible vector, or when embeddings are down.
            seen = {mem.id for mem, _ in results}
            terms = [t for t in re.findall(r"\w+", query.lower()) if len(t) > 2][:6]
            if terms:
                stmt = self._base(user_id).where(or_(*[m.Memory.content.ilike(f"%{t}%") for t in terms]))
                for mem in (await session.execute(stmt.limit(limit * 2))).scalars():
                    if mem.id not in seen and len(results) < limit:
                        results.append((mem, 0.0))
        if touch and results:
            now = utcnow()
            for mem, _ in results:
                mem.last_used_at = now
        return results

    async def list(
        self, session: AsyncSession, user_id: uuid.UUID, *, kind: str | None, limit: int, offset: int
    ) -> tuple[list[m.Memory], bool]:
        stmt = self._base(user_id)
        if kind:
            stmt = stmt.where(m.Memory.kind == kind)
        stmt = stmt.order_by(m.Memory.pinned.desc(), m.Memory.created_at.desc())
        return await repo.paginate(session, stmt, limit, offset)

    async def reindex(self, session: AsyncSession, user_id: uuid.UUID) -> int:
        stmt = (
            select(m.Memory)
            .where(
                m.Memory.user_id == user_id,
                or_(m.Memory.embedding_model.is_(None), m.Memory.embedding_model != self.embeddings.model_id),
            )
            .limit(500)
        )
        rows = list((await session.execute(stmt)).scalars())
        if not rows:
            return 0
        vectors = await self.embeddings.embed([r.content for r in rows])
        for mem, vec in zip(rows, vectors, strict=True):
            mem.embedding = vec
            mem.embedding_model = self.embeddings.model_id
        await session.flush()
        return len(rows)

    @staticmethod
    async def count(session: AsyncSession, user_id: uuid.UUID) -> int:
        stmt = select(func.count()).select_from(m.Memory).where(m.Memory.user_id == user_id)
        return int((await session.execute(stmt)).scalar_one())
