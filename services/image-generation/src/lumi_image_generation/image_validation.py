from __future__ import annotations

import hashlib
import struct
import zlib

from .model import FetchedImage, ImageGenerationSpec, OutputFormat, ValidatedImage

_PNG = b"\x89PNG\r\n\x1a\n"
_MAX_BYTES = 100 * 1024 * 1024


class ImageValidationError(ValueError):
    pass


def _png(content: bytes) -> tuple[int, int, bool]:
    if not content.startswith(_PNG):
        raise ImageValidationError("IMAGE_PNG_SIGNATURE_INVALID")
    offset = len(_PNG)
    width = height = color_type = None
    idat = bytearray()
    complete = False
    has_trns = False
    while offset < len(content):
        if offset + 12 > len(content):
            raise ImageValidationError("IMAGE_PNG_CHUNK_TRUNCATED")
        length = struct.unpack(">I", content[offset : offset + 4])[0]
        kind = content[offset + 4 : offset + 8]
        start = offset + 8
        end = start + length
        crc_end = end + 4
        if crc_end > len(content):
            raise ImageValidationError("IMAGE_PNG_CHUNK_LENGTH_INVALID")
        data = content[start:end]
        expected = struct.unpack(">I", content[end:crc_end])[0]
        actual = zlib.crc32(kind)
        actual = zlib.crc32(data, actual) & 0xFFFFFFFF
        if actual != expected:
            raise ImageValidationError("IMAGE_PNG_CRC_INVALID")
        if kind == b"IHDR":
            if length != 13 or width is not None:
                raise ImageValidationError("IMAGE_PNG_IHDR_INVALID")
            width, height = struct.unpack(">II", data[:8])
            color_type = data[9]
        elif kind == b"IDAT":
            idat.extend(data)
        elif kind == b"tRNS":
            has_trns = True
        elif kind == b"IEND":
            complete = True
            if crc_end != len(content):
                raise ImageValidationError("IMAGE_PNG_TRAILING_BYTES")
            break
        offset = crc_end
    if not width or not height or color_type is None or not idat or not complete:
        raise ImageValidationError("IMAGE_PNG_DATA_INCOMPLETE")
    try:
        zlib.decompress(bytes(idat))
    except zlib.error as exc:
        raise ImageValidationError("IMAGE_PNG_DECODE_INVALID") from exc
    return width, height, color_type in {4, 6} or has_trns


def _jpeg(content: bytes) -> tuple[int, int, bool]:
    if not content.startswith(b"\xff\xd8") or not content.endswith(b"\xff\xd9"):
        raise ImageValidationError("IMAGE_JPEG_CONTAINER_INVALID")
    offset = 2
    sof = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
    while offset < len(content) - 2:
        if content[offset] != 0xFF:
            offset += 1
            continue
        while offset < len(content) and content[offset] == 0xFF:
            offset += 1
        if offset >= len(content):
            break
        marker = content[offset]
        offset += 1
        if marker in {0x01, *range(0xD0, 0xD8), 0xD8, 0xD9}:
            continue
        if offset + 2 > len(content):
            raise ImageValidationError("IMAGE_JPEG_SEGMENT_TRUNCATED")
        length = struct.unpack(">H", content[offset : offset + 2])[0]
        if length < 2 or offset + length > len(content):
            raise ImageValidationError("IMAGE_JPEG_SEGMENT_LENGTH_INVALID")
        if marker in sof:
            if length < 7:
                raise ImageValidationError("IMAGE_JPEG_SOF_INVALID")
            height = struct.unpack(">H", content[offset + 3 : offset + 5])[0]
            width = struct.unpack(">H", content[offset + 5 : offset + 7])[0]
            if width <= 0 or height <= 0:
                raise ImageValidationError("IMAGE_JPEG_DIMENSIONS_INVALID")
            return width, height, False
        if marker == 0xDA:
            break
        offset += length
    raise ImageValidationError("IMAGE_JPEG_DIMENSIONS_UNAVAILABLE")


def _webp(content: bytes) -> tuple[int, int, bool]:
    if len(content) < 30 or content[:4] != b"RIFF" or content[8:12] != b"WEBP":
        raise ImageValidationError("IMAGE_WEBP_CONTAINER_INVALID")
    kind = content[12:16]
    size = struct.unpack("<I", content[16:20])[0]
    data = content[20 : 20 + size]
    if len(data) < size:
        raise ImageValidationError("IMAGE_WEBP_CHUNK_TRUNCATED")
    if kind == b"VP8X":
        if len(data) < 10:
            raise ImageValidationError("IMAGE_WEBP_VP8X_INVALID")
        return (
            1 + int.from_bytes(data[4:7], "little"),
            1 + int.from_bytes(data[7:10], "little"),
            bool(data[0] & 0x10),
        )
    if kind == b"VP8L":
        if len(data) < 5 or data[0] != 0x2F:
            raise ImageValidationError("IMAGE_WEBP_VP8L_INVALID")
        b1, b2, b3, b4 = data[1:5]
        width = 1 + (b1 | ((b2 & 0x3F) << 8))
        height = 1 + ((b2 >> 6) | (b3 << 2) | ((b4 & 0x0F) << 10))
        return width, height, True
    raise ImageValidationError("IMAGE_WEBP_PRIMARY_CHUNK_UNSUPPORTED")


def validate_provider_image(fetched: FetchedImage, spec: ImageGenerationSpec) -> ValidatedImage:
    content = fetched.content
    if not content:
        raise ImageValidationError("IMAGE_OUTPUT_EMPTY")
    if len(content) > _MAX_BYTES:
        raise ImageValidationError("IMAGE_OUTPUT_TOO_LARGE")
    if content.startswith(_PNG):
        mime, (width, height, alpha) = "image/png", _png(content)
    elif content.startswith(b"\xff\xd8"):
        mime, (width, height, alpha) = "image/jpeg", _jpeg(content)
    elif content.startswith(b"RIFF"):
        mime, (width, height, alpha) = "image/webp", _webp(content)
    else:
        raise ImageValidationError("IMAGE_MIME_UNSUPPORTED_OR_CORRUPT")
    if fetched.declared_mime_type is not None and fetched.declared_mime_type != mime:
        raise ImageValidationError("IMAGE_DECLARED_MIME_MISMATCH")
    expected = {
        OutputFormat.PNG: "image/png",
        OutputFormat.JPEG: "image/jpeg",
        OutputFormat.WEBP: "image/webp",
    }[spec.output_requirements.format]
    if mime != expected:
        raise ImageValidationError("IMAGE_OUTPUT_FORMAT_MISMATCH")
    if spec.output_requirements.exact_dimensions:
        if (width, height) != (spec.target_width, spec.target_height):
            raise ImageValidationError("IMAGE_OUTPUT_DIMENSIONS_MISMATCH")
    if spec.output_requirements.minimum_width and width < spec.output_requirements.minimum_width:
        raise ImageValidationError("IMAGE_OUTPUT_WIDTH_BELOW_MINIMUM")
    if spec.output_requirements.minimum_height and height < spec.output_requirements.minimum_height:
        raise ImageValidationError("IMAGE_OUTPUT_HEIGHT_BELOW_MINIMUM")
    if spec.output_requirements.transparent_background and not alpha:
        raise ImageValidationError("IMAGE_OUTPUT_ALPHA_REQUIRED")
    return ValidatedImage(
        content,
        mime,
        width,
        height,
        hashlib.sha256(content).hexdigest(),
        alpha,
    )
