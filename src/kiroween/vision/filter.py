"""Message filtering for context optimization."""

import re
from typing import TYPE_CHECKING

from kiroween.utils.logging import get_logger

if TYPE_CHECKING:
    from kiroween.agent.state import SlackMessage

logger = get_logger(__name__)

# Patterns indicating high-signal messages
HIGH_SIGNAL_PATTERNS = [
    r"\bdecided?\b",
    r"\bdecision\b",
    r"\bagreed?\b",
    r"\blet'?s\b",
    r"\bblocked?\b",
    r"\bblocker\b",
    r"\bquestion\b",
    r"\?$",  # Questions
    r"\baction\s*item\b",
    r"\btask\b",
    r"\btodo\b",
    r"\bdeadline\b",
    r"\bby\s+(monday|tuesday|wednesday|thursday|friday|eod|eow)",
    r"\burgent\b",
    r"\bpriority\b",
    r"\bplease\b",
    r"\bcan\s+you\b",
    r"\bwill\s+you\b",
    r"\bneed\s+to\b",
    r"\bshould\s+we\b",
    r"\bwhat\s+if\b",
    r"\bhow\s+about\b",
]

# Patterns indicating low-signal messages
LOW_SIGNAL_PATTERNS = [
    r"^(ok|okay|sure|thanks|thank you|ty|np|no problem|sounds good|lgtm|:[\w]+:)$",
    r"^\+1$",
    r"^(yes|no|yep|nope|yeah)$",
]

# Compiled patterns for efficiency
HIGH_SIGNAL_RE = [re.compile(p, re.IGNORECASE) for p in HIGH_SIGNAL_PATTERNS]
LOW_SIGNAL_RE = [re.compile(p, re.IGNORECASE) for p in LOW_SIGNAL_PATTERNS]


class MessageFilter:
    """Filters messages to keep high-signal content for vision processing."""

    def __init__(self, max_messages: int = 100):
        """Initialize filter.

        Args:
            max_messages: Maximum messages to keep after filtering.
        """
        self.max_messages = max_messages

    def filter_messages(
        self,
        messages: list["SlackMessage"],
        keep_with_files: bool = True,
    ) -> list["SlackMessage"]:
        """Filter messages to keep high-signal content.

        Args:
            messages: List of Slack messages.
            keep_with_files: Always keep messages with file attachments.

        Returns:
            Filtered list of messages, sorted chronologically.
        """
        scored_messages = []

        for msg in messages:
            score = self._score_message(msg, keep_with_files)
            if score > 0:
                scored_messages.append((score, msg))

        # Sort by score (descending) then by timestamp (ascending for chronological)
        scored_messages.sort(key=lambda x: (-x[0], x[1].get("timestamp", "")))

        # Take top N messages
        filtered = [msg for _, msg in scored_messages[: self.max_messages]]

        # Re-sort chronologically
        filtered.sort(key=lambda x: x.get("timestamp", ""))

        logger.info(
            "messages_filtered",
            original_count=len(messages),
            filtered_count=len(filtered),
        )

        return filtered

    def _score_message(self, msg: "SlackMessage", keep_with_files: bool) -> int:
        """Score a message for signal value.

        Args:
            msg: Slack message to score.
            keep_with_files: Give high score to messages with files.

        Returns:
            Integer score (0 means skip, higher is more important).
        """
        text = msg.get("text", "").strip()
        score = 0

        # Low signal patterns - skip these
        for pattern in LOW_SIGNAL_RE:
            if pattern.match(text):
                return 0

        # Base score for having substantial content
        if len(text) > 20:
            score += 1

        # High signal patterns
        for pattern in HIGH_SIGNAL_RE:
            if pattern.search(text):
                score += 2

        # Messages with files are valuable for vision processing
        files = msg.get("files", [])
        if keep_with_files and files:
            # Check if any file is an image
            has_image = any(
                f.get("mimetype", "").startswith("image/") for f in files
            )
            if has_image:
                score += 10  # High priority for images
            else:
                score += 3  # Still valuable for other files

        # Reactions indicate importance
        reactions = msg.get("reactions", [])
        if reactions:
            score += len(reactions)

        return score
