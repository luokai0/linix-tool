# imgx — Image Toolkit

Resize, compress, convert, thumbnail, crop, and compare images — all with Pillow.

## Install

```bash
pip install Pillow
```

## Features

- **info** — Show image metadata (format, size, mode, file size)
- **resize** — Resize to exact dimensions
- **thumb** — Generate 128x128 thumbnail
- **compress** — Compress JPEG with quality setting
- **togray** — Convert to grayscale
- **crop** — Crop a region from image
- **compare** — Compare two images for similarity

## Usage

```bash
python3 imgx.py info photo.jpg
python3 imgx.py resize photo.jpg 800 600 out.jpg
python3 imgx.py thumb photo.jpg thumb.jpg
python3 imgx.py compress photo.jpg 70 out.jpg
python3 imgx.py togray photo.jpg gray.jpg
python3 imgx.py crop photo.jpg 100 100 300 300 crop.jpg
python3 imgx.py compare a.jpg b.jpg
```

## License

MIT — luokai