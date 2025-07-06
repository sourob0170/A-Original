#!/usr/bin/env python3
"""Generate default thumbnail icons for different media types"""

from pathlib import Path


def create_svg_thumbnail(icon, color, bg_color, filename):
    """Create an SVG thumbnail with icon and colors"""
    svg_content = f'''<svg width="300" height="200" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" style="stop-color:{bg_color};stop-opacity:1" />
      <stop offset="100%" style="stop-color:{bg_color}dd;stop-opacity:1" />
    </linearGradient>
  </defs>
  <rect width="300" height="200" fill="url(#bg)" rx="12"/>
  <text x="150" y="120" font-family="Arial, sans-serif" font-size="48"
        text-anchor="middle" fill="{color}">{icon}</text>
</svg>'''

    with open(filename, "w") as f:
        f.write(svg_content)


def main():
    """Generate all default thumbnails"""
    # Create icons directory if it doesn't exist
    icons_dir = Path(__file__).parent
    icons_dir.mkdir(exist_ok=True)

    # Define thumbnails to create
    thumbnails = [
        ("🎬", "#e50914", "#2a2a2a", "default-video.svg"),
        ("🎵", "#1db954", "#2a2a2a", "default-audio.svg"),
        ("🖼️", "#ff6b6b", "#2a2a2a", "default-image.svg"),
        ("📄", "#4285f4", "#2a2a2a", "default-document.svg"),
        ("📁", "#6c757d", "#2a2a2a", "default-file.svg"),
    ]

    for icon, color, bg_color, filename in thumbnails:
        filepath = icons_dir / filename
        create_svg_thumbnail(icon, color, bg_color, str(filepath))
        print(f"Created: {filename}")

    print("All default thumbnails generated successfully!")


if __name__ == "__main__":
    main()
