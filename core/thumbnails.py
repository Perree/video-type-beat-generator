"""
Thumbnail generator for Type Beat videos using Pillow.
Generates YouTube-ready thumbnails with beat name, "Type Beat" text, and optional channel logo.
"""

import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from typing import Optional, Tuple


class ThumbnailGenerator:
    """Generate thumbnails for Type Beat videos."""

    # YouTube standard thumbnail size
    DEFAULT_WIDTH = 1280
    DEFAULT_HEIGHT = 720

    # Common image formats supported
    SUPPORTED_FORMATS = ('.jpg', '.jpeg', '.jfif', '.png', '.gif', '.bmp', '.webp', '.tiff', '.tif', '.heic')

    def __init__(self, bg_image_path: str, output_dir: str = 'thumbnails'):
        """
        Initialize thumbnail generator.

        Args:
            bg_image_path: Path to background image
            output_dir: Directory to save thumbnails
        """
        self.bg_image_path = bg_image_path
        self.output_dir = output_dir
        self.width = self.DEFAULT_WIDTH
        self.height = self.DEFAULT_HEIGHT

        Path(output_dir).mkdir(parents=True, exist_ok=True)

        if not os.path.exists(bg_image_path):
            raise FileNotFoundError(f"Background image not found: {bg_image_path}")

    def _load_background(self) -> Image.Image:
        """Load and resize background image to standard dimensions."""
        try:
            bg = Image.open(self.bg_image_path)

            # Convert RGBA to RGB if needed
            if bg.mode == 'RGBA':
                bg = bg.convert('RGB')

            # Resize to YouTube standard
            bg = bg.resize((self.width, self.height), Image.Resampling.LANCZOS)
            return bg
        except Exception as e:
            raise RuntimeError(f"Error loading background image: {e}")

    def _get_font(self, size: int) -> ImageFont.FreeTypeFont:
        """Get font for text rendering. Falls back to default if custom fonts unavailable."""
        font_paths = [
            '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
            '/System/Library/Fonts/Helvetica.ttc',
            'C:\\Windows\\Fonts\\arial.ttf',
        ]

        for font_path in font_paths:
            if os.path.exists(font_path):
                try:
                    return ImageFont.truetype(font_path, size)
                except Exception:
                    continue

        # Fallback to default font
        return ImageFont.load_default()

    def _add_text_with_shadow(self, draw: ImageDraw.ImageDraw, text: str,
                             position: Tuple[int, int], font: ImageFont.FreeTypeFont,
                             text_color: Tuple[int, int, int] = (255, 255, 255),
                             shadow_color: Tuple[int, int, int] = (0, 0, 0),
                             shadow_offset: int = 3) -> None:
        """Draw text with shadow effect."""
        # Shadow
        shadow_pos = (position[0] + shadow_offset, position[1] + shadow_offset)
        draw.text(shadow_pos, text, font=font, fill=shadow_color)

        # Main text
        draw.text(position, text, font=font, fill=text_color)

    def generate(self, beat_name: str, logo_path: Optional[str] = None,
                channel_name: Optional[str] = None) -> str:
        """
        Generate thumbnail with beat name and optional logo.

        Args:
            beat_name: Name of the beat (e.g., "Trap Beat")
            logo_path: Optional path to channel logo
            channel_name: Optional channel name to display

        Returns:
            Path to generated thumbnail
        """
        # Load background
        thumbnail = self._load_background()
        draw = ImageDraw.Draw(thumbnail)

        # Setup fonts
        title_font = self._get_font(120)  # Large font for beat name
        subtitle_font = self._get_font(80)  # Medium font for "Type Beat"
        small_font = self._get_font(40)  # Small font for channel name

        # Draw beat name (centered, upper area)
        beat_y = 150
        beat_bbox = draw.textbbox((0, 0), beat_name, font=title_font)
        beat_width = beat_bbox[2] - beat_bbox[0]
        beat_x = (self.width - beat_width) // 2
        self._add_text_with_shadow(draw, beat_name, (beat_x, beat_y), title_font)

        # Draw "Type Beat" (centered, below beat name)
        type_beat_text = "Type Beat"
        type_y = beat_y + 140
        type_bbox = draw.textbbox((0, 0), type_beat_text, font=subtitle_font)
        type_width = type_bbox[2] - type_bbox[0]
        type_x = (self.width - type_width) // 2
        self._add_text_with_shadow(draw, type_beat_text, (type_x, type_y), subtitle_font,
                                  text_color=(255, 200, 0))  # Golden accent

        # Add logo if provided
        if logo_path and os.path.exists(logo_path):
            try:
                logo = Image.open(logo_path)
                if logo.mode == 'RGBA':
                    # Keep alpha channel for logos with transparency
                    pass
                else:
                    logo = logo.convert('RGBA')

                # Resize logo to fit in corner (max 200x200)
                logo.thumbnail((200, 200), Image.Resampling.LANCZOS)

                # Paste in top-right corner with padding
                logo_x = self.width - logo.width - 20
                logo_y = 20
                thumbnail.paste(logo, (logo_x, logo_y), logo if logo.mode == 'RGBA' else None)
            except Exception as e:
                print(f"Warning: Could not add logo: {e}")

        # Add channel name if provided
        if channel_name:
            channel_y = self.height - 80
            channel_bbox = draw.textbbox((0, 0), channel_name, font=small_font)
            channel_width = channel_bbox[2] - channel_bbox[0]
            channel_x = (self.width - channel_width) // 2
            self._add_text_with_shadow(draw, channel_name, (channel_x, channel_y), small_font,
                                      text_color=(200, 200, 200))

        # Save thumbnail
        safe_name = "".join(c for c in beat_name if c.isalnum() or c in (' ', '-', '_')).strip()
        output_path = os.path.join(self.output_dir, f"{safe_name}_thumbnail.jpg")

        # Convert to RGB for JPEG (no alpha channel)
        if thumbnail.mode == 'RGBA':
            thumbnail = thumbnail.convert('RGB')

        thumbnail.save(output_path, 'JPEG', quality=95)
        return output_path


def generate_thumbnail_batch(bg_image_path: str, beats: list, logo_path: Optional[str] = None,
                            channel_name: Optional[str] = None, output_dir: str = 'thumbnails') -> list:
    """
    Generate thumbnails for multiple beats.

    Args:
        bg_image_path: Path to background image
        beats: List of beat names
        logo_path: Optional path to channel logo
        channel_name: Optional channel name
        output_dir: Output directory for thumbnails

    Returns:
        List of generated thumbnail paths
    """
    generator = ThumbnailGenerator(bg_image_path, output_dir)
    results = []

    for beat_name in beats:
        try:
            thumb_path = generator.generate(beat_name, logo_path, channel_name)
            results.append(thumb_path)
            print(f"✓ Generated thumbnail: {thumb_path}")
        except Exception as e:
            print(f"✗ Error generating thumbnail for '{beat_name}': {e}")

    return results


if __name__ == '__main__':
    # Example usage
    import sys

    if len(sys.argv) < 2:
        print("Usage: python thumbnails.py <background_image> [logo_path] [channel_name]")
        sys.exit(1)

    bg_image = sys.argv[1]
    logo = sys.argv[2] if len(sys.argv) > 2 else None
    channel = sys.argv[3] if len(sys.argv) > 3 else None

    try:
        generator = ThumbnailGenerator(bg_image)
        thumb_path = generator.generate("Sample Beat", logo, channel)
        print(f"Thumbnail generated: {thumb_path}")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
