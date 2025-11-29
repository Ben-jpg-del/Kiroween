"""Slack MCP tool schemas and descriptions."""

from pydantic import BaseModel, Field


class ConversationsHistoryInput(BaseModel):
    """Input schema for conversations_history tool."""

    channel_id: str = Field(
        ..., description="Channel ID (Cxxxxxxxxxx) or name (#general)"
    )
    limit: str = Field(
        default="1d",
        description="Time range (1d, 7d, 1m) or message count (50)",
    )
    include_activity_messages: bool = Field(
        default=False, description="Include join/leave messages"
    )
    cursor: str | None = Field(default=None, description="Pagination cursor")


class ConversationsRepliesInput(BaseModel):
    """Input schema for conversations_replies tool."""

    channel_id: str = Field(..., description="Channel ID containing the thread")
    thread_ts: str = Field(..., description="Thread timestamp")
    limit: int = Field(default=100, ge=1, le=1000, description="Max replies to fetch")


class SearchMessagesInput(BaseModel):
    """Input schema for conversations_search_messages tool."""

    search_query: str | None = Field(
        default=None, description="Search text or Slack message URL"
    )
    filter_in_channel: str | None = Field(
        default=None, description="Limit to specific channel"
    )
    filter_users_from: str | None = Field(
        default=None, description="Filter by sender user ID"
    )
    filter_date_after: str | None = Field(
        default=None, description="Messages after this date (YYYY-MM-DD)"
    )
    filter_date_before: str | None = Field(
        default=None, description="Messages before this date (YYYY-MM-DD)"
    )
    limit: int = Field(default=20, ge=1, le=100, description="Max results")


class SendMessageInput(BaseModel):
    """Input schema for conversations_add_message tool."""

    channel_id: str = Field(..., description="Target channel ID")
    payload: str = Field(..., description="Message content (supports markdown)")
    thread_ts: str | None = Field(
        default=None, description="Thread timestamp for replies"
    )
    content_type: str = Field(
        default="text/markdown", description="Content type of the message"
    )


class ChannelsListInput(BaseModel):
    """Input schema for channels_list tool."""

    query: str | None = Field(
        default=None, description="Search query for channel name"
    )
    limit: int = Field(default=50, ge=1, le=200, description="Max channels to return")


class SearchUsersInput(BaseModel):
    """Input schema for search_users tool."""

    query: str = Field(..., description="User name or email to search")
    limit: int = Field(default=10, ge=1, le=50, description="Max users to return")


# Tool descriptions for the agent prompt
SLACK_TOOL_DESCRIPTIONS = {
    "conversations_history": (
        "Fetch message history from a Slack channel. "
        "Use for digests, catch-up summaries, and retrieving recent discussions."
    ),
    "conversations_replies": (
        "Fetch all replies in a Slack thread. "
        "Use for thread summarization and decision extraction."
    ),
    "conversations_search_messages": (
        "Search Slack messages across channels. "
        "Use to find previous discussions, FAQ answers, or specific topics."
    ),
    "channels_list": (
        "List and search Slack channels. "
        "Use to resolve channel names to IDs or discover channels."
    ),
    "search_users": (
        "Search Slack users by name or email. "
        "Use to map names to user IDs for mentions or assignments."
    ),
    "conversations_add_message": (
        "Send a message to a Slack channel or thread. "
        "Use to post summaries, confirmations, or replies."
    ),
}
