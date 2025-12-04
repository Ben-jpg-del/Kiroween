"""Slack image downloader with authentication."""

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from kiroween.config import get_settings
from kiroween.utils.errors import SlackImageDownloadError
from kiroween.utils.logging import get_logger
from kiroween.vision.schemas import ImageReference

logger = get_logger(__name__)

# Supported image MIME types
SUPPORTED_IMAGE_TYPES = frozenset([
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/gif",
    "image/webp",
])

# Max file size to download (10MB)
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024


class SlackImageDownloader:
    """Downloads images from Slack using OAuth token authentication.

    Uses the existing slack_mcp_xoxp_token for authenticated downloads.
    Requires files:read scope on the token.
    """

    def __init__(self):
        self._settings = get_settings()
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "SlackImageDownloader":
        self._client = httpx.AsyncClient(
            timeout=30.0,
            headers={
                "Authorization": f"Bearer {self._settings.slack_mcp_xoxp_token}",
            },
        )
        return self

    async def __aexit__(self, *args) -> None:
        if self._client:
            await self._client.aclose()

    def is_supported_image(self, file_type: str) -> bool:
        """Check if the file type is a supported image format."""
        return file_type.lower() in SUPPORTED_IMAGE_TYPES

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
    )
    async def download_image(self, image_ref: ImageReference) -> bytes:
        """Download an image from Slack.

        Args:
            image_ref: Reference to the Slack file.

        Returns:
            Raw image bytes.

        Raises:
            SlackImageDownloadError: If download fails.
        """
        if not self._client:
            raise SlackImageDownloadError(
                "Client not initialized. Use async context manager."
            )

        if not self.is_supported_image(image_ref.file_type):
            raise SlackImageDownloadError(
                f"Unsupported file type: {image_ref.file_type}",
                details={"file_id": image_ref.file_id},
            )

        logger.info(
            "downloading_slack_image",
            file_id=image_ref.file_id,
            file_name=image_ref.file_name,
            file_type=image_ref.file_type,
        )

        try:
            response = await self._client.get(image_ref.url_private)
            response.raise_for_status()

            content = response.content

            if len(content) > MAX_FILE_SIZE_BYTES:
                raise SlackImageDownloadError(
                    f"File too large: {len(content)} bytes (max {MAX_FILE_SIZE_BYTES})",
                    details={"file_id": image_ref.file_id},
                )

            logger.info(
                "image_downloaded",
                file_id=image_ref.file_id,
                size_bytes=len(content),
            )

            return content

        except httpx.HTTPStatusError as e:
            logger.error(
                "image_download_failed",
                file_id=image_ref.file_id,
                status_code=e.response.status_code,
            )
            raise SlackImageDownloadError(
                f"HTTP {e.response.status_code} downloading image",
                details={"file_id": image_ref.file_id, "status": e.response.status_code},
            ) from e
        except httpx.RequestError as e:
            logger.error(
                "image_download_error",
                file_id=image_ref.file_id,
                error=str(e),
            )
            raise SlackImageDownloadError(
                f"Request failed: {e}",
                details={"file_id": image_ref.file_id},
            ) from e
