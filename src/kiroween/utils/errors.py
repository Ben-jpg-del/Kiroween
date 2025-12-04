"""Custom exception classes for Kiroween."""


class KiroweenError(Exception):
    """Base exception for all Kiroween errors."""

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class MCPConnectionError(KiroweenError):
    """Failed to connect to MCP server."""

    pass


class SlackToolError(KiroweenError):
    """Error executing Slack MCP tool."""

    pass


class AgendaDBError(KiroweenError):
    """Database operation failed."""

    pass


class IntentClassificationError(KiroweenError):
    """Failed to classify user intent."""

    pass


class ConfigurationError(KiroweenError):
    """Invalid or missing configuration."""

    pass


class SlackImageDownloadError(KiroweenError):
    """Failed to download image from Slack."""

    pass


class VisionProcessingError(KiroweenError):
    """Error processing image for vision model."""

    pass


class ImageCompressionError(KiroweenError):
    """Failed to compress or resize image."""

    pass
