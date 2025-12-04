"""Image processing utilities for VLM input preparation."""

import base64
import io

from PIL import Image

from kiroween.config import get_settings
from kiroween.utils.errors import ImageCompressionError
from kiroween.utils.logging import get_logger
from kiroween.vision.schemas import ImageReference, ProcessedImage

logger = get_logger(__name__)

# JPEG quality for compression
JPEG_QUALITY = 85


class ImageProcessor:
    """Processes images for VLM input.

    Handles resizing, compression, and base64 encoding to optimize
    images for GPT-4o vision API.
    """

    def __init__(self):
        self._settings = get_settings()

    def process_image(
        self,
        image_bytes: bytes,
        image_ref: ImageReference,
        target_size: int | None = None,
    ) -> ProcessedImage:
        """Process an image for VLM input.

        Args:
            image_bytes: Raw image data.
            image_ref: Image metadata.
            target_size: Target max dimension for resizing.
                        Defaults to settings.vision_image_target_size.

        Returns:
            ProcessedImage with base64-encoded data.

        Raises:
            ImageCompressionError: If image processing fails.
        """
        if target_size is None:
            target_size = self._settings.vision_image_target_size

        original_size = len(image_bytes)

        logger.info(
            "processing_image",
            file_id=image_ref.file_id,
            original_size=original_size,
        )

        try:
            # Open and process image
            img = Image.open(io.BytesIO(image_bytes))
            original_width, original_height = img.size

            # Convert to RGB if necessary (for JPEG encoding)
            if img.mode in ("RGBA", "P", "LA"):
                # Create white background for transparent images
                background = Image.new("RGB", img.size, (255, 255, 255))
                if img.mode == "P":
                    img = img.convert("RGBA")
                background.paste(img, mask=img.split()[-1] if img.mode == "RGBA" else None)
                img = background
            elif img.mode != "RGB":
                img = img.convert("RGB")

            # Resize if larger than target
            if max(original_width, original_height) > target_size:
                img = self._resize_image(img, target_size)

            # Encode to JPEG for compression
            output_buffer = io.BytesIO()
            img.save(output_buffer, format="JPEG", quality=JPEG_QUALITY, optimize=True)
            processed_bytes = output_buffer.getvalue()

            # Base64 encode
            base64_data = base64.b64encode(processed_bytes).decode("utf-8")

            new_width, new_height = img.size

            logger.info(
                "image_processed",
                file_id=image_ref.file_id,
                original_size=original_size,
                processed_size=len(processed_bytes),
                dimensions=f"{new_width}x{new_height}",
                compression_ratio=f"{original_size / len(processed_bytes):.1f}x"
                if len(processed_bytes) > 0
                else "N/A",
            )

            return ProcessedImage(
                file_id=image_ref.file_id,
                file_name=image_ref.file_name,
                base64_data=base64_data,
                mime_type="image/jpeg",
                original_size_bytes=original_size,
                processed_size_bytes=len(processed_bytes),
                width=new_width,
                height=new_height,
            )

        except Exception as e:
            logger.error(
                "image_processing_error",
                file_id=image_ref.file_id,
                error=str(e),
            )
            raise ImageCompressionError(
                f"Failed to process image: {e}",
                details={"file_id": image_ref.file_id},
            ) from e

    def _resize_image(self, img: Image.Image, target_size: int) -> Image.Image:
        """Resize image maintaining aspect ratio."""
        width, height = img.size

        if width > height:
            new_width = target_size
            new_height = int(height * (target_size / width))
        else:
            new_height = target_size
            new_width = int(width * (target_size / height))

        return img.resize((new_width, new_height), Image.Resampling.LANCZOS)
