"""Pydantic schemas for vision processing."""

from pydantic import BaseModel, Field


class RecommendedLink(BaseModel):
    """A recommended link extracted from visual or text content."""

    label: str = Field(..., description="Short label for the link")
    url: str = Field(..., description="Full URL")


class VisionSummaryOutput(BaseModel):
    """Structured output schema for vision-enhanced summarization.

    This schema is used with GPT-4o's response_format parameter
    to ensure consistent structured output.
    """

    key_decisions: list[str] = Field(
        default_factory=list,
        max_length=3,
        description="Top 3 key decisions made in the thread/channel",
    )
    unresolved_questions: list[str] = Field(
        default_factory=list,
        max_length=4,
        description="Up to 4 unresolved questions or blockers",
    )
    recommended_links: list[RecommendedLink] = Field(
        default_factory=list,
        description="Relevant links mentioned or visible in images",
    )
    explain_for_newcomer: str = Field(
        ...,
        description="Plain-language summary for someone unfamiliar with the thread",
    )


class ImageReference(BaseModel):
    """Reference to a Slack file/image."""

    file_id: str = Field(..., description="Slack file ID")
    file_name: str = Field(..., description="Original filename")
    file_type: str = Field(..., description="MIME type (image/png, etc.)")
    url_private: str = Field(..., description="Private download URL")
    timestamp: str = Field(..., description="Message timestamp containing the file")
    user_id: str = Field(..., description="User who uploaded the file")


class ProcessedImage(BaseModel):
    """An image processed and ready for VLM input."""

    file_id: str = Field(..., description="Slack file ID")
    file_name: str = Field(..., description="Original filename")
    base64_data: str = Field(..., description="Base64-encoded image data")
    mime_type: str = Field(..., description="MIME type after processing")
    original_size_bytes: int = Field(..., description="Original file size")
    processed_size_bytes: int = Field(..., description="Processed file size")
    width: int = Field(..., description="Image width after processing")
    height: int = Field(..., description="Image height after processing")
