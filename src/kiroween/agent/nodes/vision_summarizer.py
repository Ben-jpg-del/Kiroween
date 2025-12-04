"""Vision summarizer node for image-aware thread/channel summarization."""

import json

from langchain_core.messages import AIMessage

from kiroween.agent.state import AgentState, SlackMessage
from kiroween.config import get_settings
from kiroween.llm.prompts import VISION_SUMMARIZER_PROMPT
from kiroween.llm.provider import get_llm_for_vision
from kiroween.utils.logging import get_logger
from kiroween.vision.downloader import SlackImageDownloader
from kiroween.vision.filter import MessageFilter
from kiroween.vision.processor import ImageProcessor
from kiroween.vision.schemas import ImageReference, ProcessedImage, VisionSummaryOutput

logger = get_logger(__name__)


async def vision_summarizer_node(state: AgentState) -> dict:
    """Process thread/channel with vision capabilities.

    This node:
    1. Fetches messages from the target channel/thread (via state)
    2. Filters low-signal messages
    3. Downloads and processes images
    4. Builds multi-modal input for GPT-4o
    5. Returns structured summary

    Returns:
        Dict with vision_summary and messages.
    """
    settings = get_settings()
    channel = state.get("target_channel")
    thread_ts = state.get("target_thread_ts")
    slack_messages = state.get("slack_messages", [])

    logger.info(
        "vision_summarizer_starting",
        channel=channel,
        thread_ts=thread_ts,
        message_count=len(slack_messages),
    )

    try:
        # Filter messages for high-signal content
        message_filter = MessageFilter(max_messages=100)
        filtered_messages = message_filter.filter_messages(slack_messages)

        # Extract image references
        image_refs = _extract_image_references(filtered_messages)
        logger.info("images_found", count=len(image_refs))

        # Download and process images
        processed_images: list[ProcessedImage] = []
        download_errors: list[str] = []

        if image_refs:
            async with SlackImageDownloader() as downloader:
                processor = ImageProcessor()

                for ref in image_refs[: settings.vision_max_images]:
                    try:
                        image_bytes = await downloader.download_image(ref)
                        processed = processor.process_image(image_bytes, ref)
                        processed_images.append(processed)
                    except Exception as e:
                        logger.warning(
                            "image_processing_failed",
                            file_id=ref.file_id,
                            error=str(e),
                        )
                        download_errors.append(f"{ref.file_name}: {e}")

        # Build multi-modal content for LLM
        content = _build_multimodal_content(filtered_messages, processed_images)

        # Call GPT-4o with vision
        llm = get_llm_for_vision()

        response = await llm.ainvoke(
            [
                {"role": "system", "content": VISION_SUMMARIZER_PROMPT},
                {"role": "user", "content": content},
            ],
        )

        # Parse structured output
        try:
            # Try to extract JSON from the response
            response_content = response.content
            if "```json" in response_content:
                response_content = response_content.split("```json")[1].split("```")[0]
            elif "```" in response_content:
                response_content = response_content.split("```")[1].split("```")[0]

            summary_data = json.loads(response_content.strip())
            summary = VisionSummaryOutput(**summary_data)
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning("vision_parse_error", error=str(e))
            # Fallback to unstructured response
            summary = VisionSummaryOutput(
                key_decisions=[],
                unresolved_questions=[],
                recommended_links=[],
                explain_for_newcomer=response.content,
            )

        # Format response message
        response_text = _format_vision_summary(summary, download_errors)

        logger.info(
            "vision_summarizer_completed",
            decisions_count=len(summary.key_decisions),
            questions_count=len(summary.unresolved_questions),
            images_processed=len(processed_images),
        )

        return {
            "vision_summary": summary.model_dump(),
            "messages": [AIMessage(content=response_text)],
        }

    except Exception as e:
        logger.error("vision_summarizer_error", error=str(e))
        return {
            "error": str(e),
            "messages": [
                AIMessage(
                    content=f"I encountered an error processing the visual content: {e}"
                )
            ],
        }


def _extract_image_references(messages: list[SlackMessage]) -> list[ImageReference]:
    """Extract image file references from messages."""
    refs = []

    for msg in messages:
        files = msg.get("files", [])
        for file_info in files:
            file_type = file_info.get("mimetype", "")
            if file_type.startswith("image/"):
                refs.append(
                    ImageReference(
                        file_id=file_info.get("id", ""),
                        file_name=file_info.get("name", "unknown"),
                        file_type=file_type,
                        url_private=file_info.get("url_private", ""),
                        timestamp=msg.get("timestamp", ""),
                        user_id=msg.get("user_id", ""),
                    )
                )

    return refs


def _build_multimodal_content(
    messages: list[SlackMessage],
    images: list[ProcessedImage],
) -> list[dict]:
    """Build multi-modal content array for GPT-4o vision."""
    content = []

    # Add text content - formatted message history
    text_content = "## Thread Messages\n\n"
    for msg in messages:
        user = msg.get("user_name", "Unknown")
        text = msg.get("text", "")
        ts = msg.get("timestamp", "")
        text_content += f"**{user}** ({ts}):\n{text}\n\n"

    content.append(
        {
            "type": "text",
            "text": text_content,
        }
    )

    # Add images
    for img in images:
        content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{img.mime_type};base64,{img.base64_data}",
                    "detail": "high",
                },
            }
        )
        content.append(
            {
                "type": "text",
                "text": f"[Image: {img.file_name}]",
            }
        )

    return content


def _format_vision_summary(
    summary: VisionSummaryOutput,
    errors: list[str],
) -> str:
    """Format the vision summary as a response message."""
    parts = []

    parts.append("## Summary for Newcomers")
    parts.append(summary.explain_for_newcomer)
    parts.append("")

    if summary.key_decisions:
        parts.append("## Key Decisions")
        for decision in summary.key_decisions:
            parts.append(f"- {decision}")
        parts.append("")

    if summary.unresolved_questions:
        parts.append("## Unresolved Questions")
        for question in summary.unresolved_questions:
            parts.append(f"- {question}")
        parts.append("")

    if summary.recommended_links:
        parts.append("## Recommended Links")
        for link in summary.recommended_links:
            parts.append(f"- [{link.label}]({link.url})")
        parts.append("")

    if errors:
        parts.append("---")
        parts.append(f"*Note: {len(errors)} image(s) could not be processed.*")

    return "\n".join(parts)
