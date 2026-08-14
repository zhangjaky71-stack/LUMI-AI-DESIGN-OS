from __future__ import annotations

import hashlib
import struct
import zlib

from .model import FetchedImage, ImageGenerationSpec, ValidatedImage

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
JPEG_SOI = b"\xff\xd8"
JPEG_EOI = b"\xff\xd9"
MAX_IMAGE_BYTES = 100 * 1024 * 1024


class ImageValidationError(ValueError):
    pass


def _png_metadata(content: bytes) -> tuple[int, int, bool]:
    if not content.startswith(PNG_SIGNATURE):
        raise ImageValidationError("IMAGE_PNG_SIGNATURE_INVALID")
    offset = len(PNG_SIGNATURE)
    width: int | None = None
    height: int | None = None
    color_type: int | None = None
    idat = bytearray()
    saw_iend = False
    has_trns = False
    while offset < len(content):
        if offset + 12 > len(content):
            raise ImageValidationError("IMAGE_PNG_CHUNK_TRUNCATED")
        length = struct.unpack(">I", content[offset : offset + 4])[0]
        chunk_type = content[offset + 4 : offset + 8]
        data_start = offset + 8
        data_end = data_start + length
        crc_end = data_end + 4
        if crc_end > len(content):
            raise ImageValidationError("IMAGE_PNG_CHUNK_LENGTH_INVALID")
        data = content[data_start:data_end]
        expected_crc = struct.unpack(">I", content[data_end:crc_end])[0]
        actual_crc = zlib.crc32(chunk_type)
        actual_crc = zlib.crc32(data, actual_crc) & 0xFFFFFFFF
        if expected_crc != actual_crc:
            raise ImageValidationError("IMAGE_PNG_CRC_INVALID")
        if chunk_type == b"IHDR":
            if length != 13 or width is not None:
                raise ImageValidationError("IMAGE_PNG_IHDR_INVALID")
            width, height = struct.unpack(">II", data[:8])
            color_type = data[9]
        elif chunk_type == b"IDAT":
            idat.extend(data)
        elif chunk_type == b"tRNS":
            has_trns = True
        elif chunk_type == b"IEND":
            if length != 0:
                raise ImageValidationError("IMAGE_PNG_IEND_INVALID")
            saw_iend = True
            if crc_end != len(content):
                raise ImageValidationError("IMAGE_PNG_TRAILING_BYTES")
            break
        offset = crc_end
    if width is None or height is None or color_type is None:
        raise ImageValidationError("IMAGE_PNG_IHDR_MISSING")
    if width <= 0 or height <= 0:
        raise ImageValidationError("IMAGE_PNG_DIMENSIONS_INVALID")
    if not idat or not saw_iend:
        raise ImageValidationError("IMAGE_PNG_DATA_INCOMPLETE")
    try:
        zlib.decompress(bytes(idat))
    except zlib.error as exc:
        raise ImageValidationError("IMAGE_PNG_DECODE_INVALID") from exc
    return width, height, color_type in {4, 6} or has_trns


def _jpeg_metadata(content: bytes) -> tuple[int, int, bool]:
    if not content.startswith(JPEG_SOI) or not content.endswith(JPEG_EOI):
        raise ImageValidationError("IMAGE_JPEG_CONTAINER_INVALID")
    offset = 2
    sof_markers = {
        0xC0,
        0xC1,
        0xC2,
        0xC3,
        0xC5,
        0xC6,
        0xC7,
        0xC9,
        0xCA,
        0xCB,
        0xCD,
        0xCE,
        0xCF,
    }
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
        if marker in {0x01, 0xD0, 0xD1, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7}:
            continue
        if marker in {0xD8, 0xD9}:
            continue
        if offset + 2 > len(content):
            raise ImageValidationError("IMAGE_JPEG_SEGMENT_TRUNCATED")
        segment_length = struct.unpack(">H", content[offset : offset + 2])[0]
        if segment_length < 2 or offset + segment_length > len(content):
            raise ImageValidationError("IMAGE_JPEG_SEGMENT_LENGTH_INVALID")
        if marker in sof_markers:
            if segment_length < 7:
                raise ImageValidationError("IMAGE_JPEG_SOF_INVALID")
            height = struct.unpack(">H", content[offset + 3 : offset + 5])[0]
            width = struct.unpack(">H", content[offset + 5 : offset + 7])[0]
            if width <= 0 or height <= 0:
                raise ImageValidationError("IMAGE_JPEG_DIMENSIONS_INVALID")
            return width, height, False
        if marker == 0xDA:
            break
        offset += segment_length
    raise ImageValidationError("IMAGE_JPEG_DIMENSIONS_UNAVAILABLE")


def _webp_metadata(content: bytes) -> tuple[int, int, bool]:
    if len(content) < 30 or content[:4] != b"RIFF" or content[8:12] != b"WEBP":
        raise ImageValidationError("IMAGE_WEBP_CONTAINER_INVALID")
    declared_size = struct.unpack("<I", content[4:8])[0] + 8
    if declared_size > len(content):
        raise ImageValidationError("IMAGE_WEBP_TRUNCATED")
    chunk_type = content[12:16]
    chunk_size = struct.unpack("<I", content[16:20])[0]
    data = content[20 : 20 + chunk_size]
    if len(data) < chunk_size:
        raise ImageValidationError("IMAGE_WEBP_CHUNK_TRUNCATED")
    if chunk_type == b"VP8X":
        if len(data) < 10:
            raise ImageValidationError("IMAGE_WEBP_VP8X_INVALID")
        flags = data[0]
        width = 1 + int.from_bytes(data[4:7], "little")
        height = 1 + int.from_bytes(data[7:10], "little")
        return width, height, bool(flags & 0x10)
    if chunk_type == b"VP8L":
        if len(data) < 5 or data[0] != 0x2F:
            raise ImageValidationError("IMAGE_WEBP_VP8L_INVALID")
        b1, b2, b3, b4 = data[1:5]
        width = 1 + (b1 | ((b2 & 0x3F) << 8))
        height = 1 + ((b2 >> 6) | (b3 << 2) | ((b4 & 0x0F) << 10))
        return width, height, True
    if chunk_type == b"VP8 ":
        if len(data) < 10 or data[3:6] != b"\x9d\x01\x2a":
            raise ImageValidationError("IMAGE_WEBP_VP8_INVALID")
        width = int.from_bytes(data[6:8], "little") & 0x3FFF
        height = int.from_bytes(data[8:10], "little") & 0x3FFF
        if width <= 0 or height <= 0:
            raise ImageValidationError("IMAGE_WEBP_DIMENSIONS_INVALID")
        return width, height, False
    raise ImageValidationError("IMAGE_WEBP_PRIMARY_CHUNK_UNSUPPORTED")


def _sniff(content: bytes) -> tuple[str, int, int, bool]:
    if content.startswith(PNG_SIGNATURE):
        width, height, has_alpha = _png_metadata(content)
        return "image/png", width, height, has_alpha
    if content.startswith(JPEG_SOI):
        width, height, has_alpha = _jpeg_metadata(content)
        return "image/jpeg", width, height, has_alpha
    if content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        width, height, has_alpha = _webp_metadata(content)
        return "image/webp", width, height, has_alpha
    raise ImageValidationError("IMAGE_MIME_UNSUPPORTED_OR_CORRUPT")


def validate_provider_image(fetched: FetchedImage, spec: ImageGenerationSpec) -> ValidatedImage:
    content = fetched.content
    if not content:
        raise ImageValidationError("IMAGE_OUTPUT_EMPTY")
    if len(content) > MAX_IMAGE_BYTES:
        raise ImageValidationError("IMAGE_OUTPUT_TOO_LARGE")

    mime_type, width, height, has_alpha = _sniff(content)
    if fetched.declared_mime_type is not None and fetched.declared_mime_type != mime_type:
        raise ImageValidationError("IMAGE_DECLARED_MIME_MISMATCH")

    expected_mime = {
        "PNG": "image/png",
        "JPEG": "image/jpeg",
        "WEBP": "image/webp",
    }[spec.output_requirements.format]
    if mime_type != expected_mime:
        raise ImageValidationError("IMAGE_OUTPUT_FORMAT_MISMATCH")

    if spec.output_requirements.exact_dimensions:
        if width != spec.target_width or height != spec.target_height:
            raise ImageValidationError("IMAGE_OUTPUT_DIMENSIONS_MISMATCH")
    if spec.output_requirements.minimum_width is not None:
        if width < spec.output_requirements.minimum_width:
            raise ImageValidationError("IMAGE_OUTPUT_WIDTH_BELOW_MINIMUM")
    if spec.output_requirements.minimum_height is not None:
        if height < spec.output_requirements.minimum_height:
            raise ImageValidationError("IMAGE_OUTPUT_HEIGHT_BELOW_MINIMUM")
    if spec.output_requirements.transparent_background and not has_alpha:
        raise ImageValidationError("IMAGE_OUTPUT_ALPHA_REQUIRED")

    return ValidatedImage(
        content=content,
        mime_type=mime_type,
        width=width,
        height=height,
        checksum_sha256=hashlib.sha256(content).hexdigest(),
        has_alpha=has_alpha,
    )
