"""Search and knowledge management service."""

from datetime import datetime
from typing import Any

from sqlalchemy import and_, or_, select

from kiroween.agenda.models import AgendaItem, FAQAnswer, ItemStatus, ItemType
from kiroween.agenda.repository import AgendaRepository
from kiroween.agenda.service import AgendaService
from kiroween.utils.logging import get_logger

logger = get_logger(__name__)


class SearchService:
    """Service for structured search over agenda items."""

    def __init__(self):
        self.agenda_service = AgendaService()

    async def search_decisions_about(
        self,
        topic: str,
        workspace_id: str | None = None,
        limit: int = 20,
    ) -> list[AgendaItem]:
        """Search for decisions about a specific topic."""
        async with self.agenda_service.get_repository() as repo:
            stmt = select(AgendaItem).where(
                and_(
                    AgendaItem.type == ItemType.DECISION,
                    or_(
                        AgendaItem.title.ilike(f"%{topic}%"),
                        AgendaItem.description.ilike(f"%{topic}%"),
                        AgendaItem.project.ilike(f"%{topic}%"),
                    ),
                )
            )

            if workspace_id:
                stmt = stmt.where(AgendaItem.workspace_id == workspace_id)

            stmt = stmt.order_by(AgendaItem.created_at.desc()).limit(limit)
            result = await repo.session.execute(stmt)
            return list(result.scalars().all())

    async def search_tasks_with_text(
        self,
        text: str,
        assigned_to: str | None = None,
        workspace_id: str | None = None,
        limit: int = 20,
    ) -> list[AgendaItem]:
        """Search tasks assigned to a user containing specific text."""
        async with self.agenda_service.get_repository() as repo:
            stmt = select(AgendaItem).where(
                and_(
                    AgendaItem.type == ItemType.TASK,
                    or_(
                        AgendaItem.title.ilike(f"%{text}%"),
                        AgendaItem.description.ilike(f"%{text}%"),
                        AgendaItem.raw_snippet.ilike(f"%{text}%"),
                    ),
                )
            )

            if assigned_to:
                stmt = stmt.where(AgendaItem.assigned_to_user_id == assigned_to)

            if workspace_id:
                stmt = stmt.where(AgendaItem.workspace_id == workspace_id)

            stmt = stmt.order_by(AgendaItem.updated_at.desc()).limit(limit)
            result = await repo.session.execute(stmt)
            return list(result.scalars().all())

    async def search_open_questions(
        self,
        asked_by: str | None = None,
        days: int = 7,
        workspace_id: str | None = None,
        limit: int = 20,
    ) -> list[AgendaItem]:
        """Search open questions asked by a user in the last N days."""
        from datetime import timedelta

        cutoff_date = datetime.utcnow() - timedelta(days=days)

        async with self.agenda_service.get_repository() as repo:
            stmt = select(AgendaItem).where(
                and_(
                    AgendaItem.type == ItemType.QUESTION,
                    AgendaItem.status == ItemStatus.OPEN,
                    AgendaItem.created_at >= cutoff_date,
                )
            )

            if asked_by:
                stmt = stmt.where(AgendaItem.created_by_user_id == asked_by)

            if workspace_id:
                stmt = stmt.where(AgendaItem.workspace_id == workspace_id)

            stmt = stmt.order_by(AgendaItem.created_at.desc()).limit(limit)
            result = await repo.session.execute(stmt)
            return list(result.scalars().all())

    async def structured_search(
        self,
        filters: dict[str, Any],
        workspace_id: str | None = None,
        limit: int = 50,
    ) -> list[AgendaItem]:
        """Perform structured search with multiple filters."""
        async with self.agenda_service.get_repository() as repo:
            stmt = select(AgendaItem)

            conditions = []

            # Type filter
            if item_type := filters.get("type"):
                if isinstance(item_type, list):
                    types = [ItemType(t) for t in item_type]
                    conditions.append(AgendaItem.type.in_(types))
                else:
                    conditions.append(AgendaItem.type == ItemType(item_type))

            # Status filter
            if status := filters.get("status"):
                if isinstance(status, list):
                    statuses = [ItemStatus(s) for s in status]
                    conditions.append(AgendaItem.status.in_(statuses))
                else:
                    conditions.append(AgendaItem.status == ItemStatus(status))

            # Assignee filter
            if assigned_to := filters.get("assigned_to"):
                conditions.append(AgendaItem.assigned_to_user_id == assigned_to)

            # Requestor filter
            if requestor := filters.get("requestor"):
                conditions.append(AgendaItem.requestor_user_id == requestor)

            # Project filter
            if project := filters.get("project"):
                conditions.append(AgendaItem.project == project)

            # Text search
            if query := filters.get("query"):
                conditions.append(
                    or_(
                        AgendaItem.title.ilike(f"%{query}%"),
                        AgendaItem.description.ilike(f"%{query}%"),
                        AgendaItem.raw_snippet.ilike(f"%{query}%"),
                    )
                )

            # Date range
            if date_from := filters.get("date_from"):
                if isinstance(date_from, str):
                    date_from = datetime.fromisoformat(date_from)
                conditions.append(AgendaItem.created_at >= date_from)

            if date_to := filters.get("date_to"):
                if isinstance(date_to, str):
                    date_to = datetime.fromisoformat(date_to)
                conditions.append(AgendaItem.created_at <= date_to)

            # Channel filter
            if channel_id := filters.get("channel_id"):
                conditions.append(AgendaItem.source_channel_id == channel_id)

            if workspace_id:
                conditions.append(AgendaItem.workspace_id == workspace_id)

            if conditions:
                stmt = stmt.where(and_(*conditions))

            # Ordering
            order_by = filters.get("order_by", "updated_at_desc")
            if order_by == "created_at_desc":
                stmt = stmt.order_by(AgendaItem.created_at.desc())
            elif order_by == "due_date_asc":
                stmt = stmt.order_by(AgendaItem.due_date.asc().nulls_last())
            else:
                stmt = stmt.order_by(AgendaItem.updated_at.desc())

            stmt = stmt.limit(limit)
            result = await repo.session.execute(stmt)
            return list(result.scalars().all())


class KnowledgeService:
    """Service for FAQ and canonical answer management."""

    def __init__(self):
        self.agenda_service = AgendaService()

    async def create_faq_answer(
        self,
        workspace_id: str,
        question: str,
        answer: str,
        source_thread_ts: str | None = None,
        source_channel_id: str | None = None,
        source_message_ts: str | None = None,
        tags: list[str] | None = None,
        is_canonical: bool = False,
    ) -> FAQAnswer:
        """Create an FAQ answer from a thread."""
        async with self.agenda_service.get_repository() as repo:
            faq = FAQAnswer(
                workspace_id=workspace_id,
                question=question,
                answer=answer,
                source_thread_ts=source_thread_ts,
                source_channel_id=source_channel_id,
                source_message_ts=source_message_ts,
                tags=",".join(tags) if tags else None,
                is_canonical=is_canonical,
            )
            repo.session.add(faq)
            await repo.session.commit()
            await repo.session.refresh(faq)

            logger.info("created_faq_answer", faq_id=faq.id, question=question[:50])
            return faq

    async def search_faq(
        self,
        query: str,
        workspace_id: str | None = None,
        limit: int = 10,
    ) -> list[FAQAnswer]:
        """Search FAQ answers by question or answer text."""
        async with self.agenda_service.get_repository() as repo:
            stmt = select(FAQAnswer).where(
                or_(
                    FAQAnswer.question.ilike(f"%{query}%"),
                    FAQAnswer.answer.ilike(f"%{query}%"),
                )
            )

            if workspace_id:
                stmt = stmt.where(FAQAnswer.workspace_id == workspace_id)

            stmt = stmt.order_by(
                FAQAnswer.is_canonical.desc(),
                FAQAnswer.usage_count.desc(),
            ).limit(limit)

            result = await repo.session.execute(stmt)
            return list(result.scalars().all())

    async def find_similar_question(
        self,
        question: str,
        workspace_id: str | None = None,
        threshold: float = 0.7,
    ) -> FAQAnswer | None:
        """Find if a similar question has been answered before."""
        # Simple keyword-based similarity (could be enhanced with embeddings)
        question_lower = question.lower()
        question_words = set(question_lower.split())

        async with self.agenda_service.get_repository() as repo:
            stmt = select(FAQAnswer)
            if workspace_id:
                stmt = stmt.where(FAQAnswer.workspace_id == workspace_id)

            result = await repo.session.execute(stmt)
            all_faqs = list(result.scalars().all())

            best_match = None
            best_score = 0.0

            for faq in all_faqs:
                faq_question_lower = faq.question.lower()
                faq_words = set(faq_question_lower.split())

                # Simple Jaccard similarity
                intersection = question_words & faq_words
                union = question_words | faq_words
                if union:
                    similarity = len(intersection) / len(union)
                    if similarity > best_score and similarity >= threshold:
                        best_score = similarity
                        best_match = faq

            if best_match:
                # Increment usage count
                best_match.usage_count += 1
                best_match.updated_at = datetime.utcnow()
                await repo.session.commit()
                await repo.session.refresh(best_match)

            return best_match

    async def promote_to_canonical(
        self,
        faq_id: str,
    ) -> FAQAnswer | None:
        """Promote an FAQ answer to canonical."""
        async with self.agenda_service.get_repository() as repo:
            result = await repo.session.execute(
                select(FAQAnswer).where(FAQAnswer.id == faq_id)
            )
            faq = result.scalar_one_or_none()

            if not faq:
                return None

            faq.is_canonical = True
            faq.updated_at = datetime.utcnow()
            await repo.session.commit()
            await repo.session.refresh(faq)

            logger.info("promoted_to_canonical", faq_id=faq_id)
            return faq

    async def get_faq_by_id(self, faq_id: str) -> FAQAnswer | None:
        """Get FAQ answer by ID."""
        async with self.agenda_service.get_repository() as repo:
            result = await repo.session.execute(
                select(FAQAnswer).where(FAQAnswer.id == faq_id)
            )
            return result.scalar_one_or_none()


def get_search_service() -> SearchService:
    """Get the global search service instance."""
    return SearchService()


def get_knowledge_service() -> KnowledgeService:
    """Get the global knowledge service instance."""
    return KnowledgeService()

