"""Vision processing module for image-aware Slack summarization."""

from kiroween.vision.schemas import (
    ImageReference,
    ProcessedImage,
    RecommendedLink,
    VisionSummaryOutput,
)
from kiroween.vision.downloader import SlackImageDownloader
from kiroween.vision.processor import ImageProcessor
from kiroween.vision.filter import MessageFilter

__all__ = [
    "ImageReference",
    "ProcessedImage",
    "RecommendedLink",
    "VisionSummaryOutput",
    "SlackImageDownloader",
    "ImageProcessor",
    "MessageFilter",
]
