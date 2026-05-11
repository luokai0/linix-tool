#!/usr/bin/env python3
"""
imgx — Image toolkit
Resize, convert, compress, thumbnail, info, crop, watermark

Usage:
  imgx.py info <file>                    -- show image metadata
  imgx.py resize <file> <w> <h> <out>    -- resize image
  imgx.py thumb <file> <out>             -- 128x128 thumbnail
  imgx.py compress <file> <quality> <out> -- compress JPEG
  imgx.py togray <file> <out>            -- convert to grayscale
  imgx.py crop <file> <x> <y> <w> <h> <out>  -- crop region
  imgx.py compare <file1> <file2>        -- diff two images
"""

import sys
from pathlib import Path
from PIL import Image


def get_info(filepath: str) -> dict:
    img = Image.open(filepath)
    return {
        'format': img.format,
        'mode': img.mode,
        'size': f"{img.width}x{img.height}",
        'file': str(Path(filepath).stat().st_size / 1024) + " KB"
    }


def resize_image(input_path: str, w: int, h: int, output_path: str):
    img = Image.open(input_path)
    resized = img.resize((w, h), Image.LANCZOS)
    resized.save(output_path)


def thumbnail(input_path: str, output_path: str, size: int = 128):
    img = Image.open(input_path)
    img.thumbnail((size, size), Image.LANCZOS)
    img.save(output_path)


def compress(input_path: str, quality: int, output_path: str):
    img = Image.open(input_path)
    if img.mode in ('RGBA', 'P'):
        img = img.convert('RGB')
    img.save(output_path, 'JPEG', quality=quality, optimize=True)


def to_grayscale(input_path: str, output_path: str):
    img = Image.open(input_path)
    gray = img.convert('L')
    gray.save(output_path)


def crop_image(input_path: str, x: int, y: int, w: int, h: int, output_path: str):
    img = Image.open(input_path)
    cropped = img.crop((x, y, x+w, y+h))
    cropped.save(output_path)


def compare_images(f1: str, f2: str) -> dict:
    img1 = Image.open(f1).convert('RGB')
    img2 = Image.open(f2).convert('RGB')
    if img1.size != img2.size:
        return {'match': False, 'reason': 'different sizes'}
    diff = 0
    p1, p2 = list(img1.getdata()), list(img2.getdata())
    for a, b in zip(p1, p2):
        diff += sum(abs(a[i]-b[i]) for i in range(3))
    max_diff = 255 * 3 * len(p1)
    similarity = (1 - diff/max_diff) * 100
    return {'match': similarity > 99, 'similarity': f"{similarity:.2f}%"}


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    cmd = sys.argv[1]

    if cmd == 'info' and len(sys.argv) >= 3:
        info = get_info(sys.argv[2])
        for k, v in info.items():
            print(f"  {k:8s}  {v}")
    elif cmd == 'resize' and len(sys.argv) >= 6:
        resize_image(sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), sys.argv[5])
        print(f"✅ Resized to {sys.argv[3]}x{sys.argv[4]}")
    elif cmd == 'thumb' and len(sys.argv) >= 4:
        thumbnail(sys.argv[2], sys.argv[3])
        print(f"✅ Thumbnail saved to {sys.argv[3]}")
    elif cmd == 'compress' and len(sys.argv) >= 5:
        compress(sys.argv[2], int(sys.argv[3]), sys.argv[4])
        orig = Path(sys.argv[2]).stat().st_size
        new = Path(sys.argv[4]).stat().st_size
        print(f"✅ Compressed {orig//1024}KB → {new//1024}KB ({100*new//orig}%)")
    elif cmd == 'togray' and len(sys.argv) >= 4:
        to_grayscale(sys.argv[2], sys.argv[3])
        print(f"✅ Grayscale saved to {sys.argv[3]}")
    elif cmd == 'crop' and len(sys.argv) >= 8:
        crop_image(sys.argv[2], *[int(x) for x in sys.argv[3:7]], sys.argv[7])
        print(f"✅ Cropped to {sys.argv[5]}x{sys.argv[6]}")
    elif cmd == 'compare' and len(sys.argv) >= 4:
        result = compare_images(sys.argv[2], sys.argv[3])
        print(f"  match:     {result['match']}")
        print(f"  similarity: {result['similarity']}")
    else:
        print(__doc__)