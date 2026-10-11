import struct

MIN_REEL_SECONDS = 3
MAX_REEL_SECONDS = 15 * 60
MIN_ASPECT_RATIO = 0.01
MAX_ASPECT_RATIO = 10.0


def _boxes(data: bytes, start: int, end: int):
    position = start
    while position + 8 <= end:
        size, kind = struct.unpack_from(">I4s", data, position)
        header = 8
        if size == 1:
            if position + 16 > end:
                return
            size = struct.unpack_from(">Q", data, position + 8)[0]
            header = 16
        elif size == 0:
            size = end - position
        if size < header or position + size > end:
            return
        yield kind, position + header, position + size
        position += size


def validate_reel_video(content: bytes) -> str | None:
    """Return a user-facing problem, or None when valid or when it can't be parsed."""
    duration_seconds: float | None = None
    ratio: float | None = None
    for kind, body, box_end in _boxes(content, 0, len(content)):
        if kind != b"moov":
            continue
        for child, child_body, child_end in _boxes(content, body, box_end):
            if child == b"mvhd" and child_end - child_body >= 24:
                version = content[child_body]
                if version == 1 and child_end - child_body >= 32:
                    timescale, duration = struct.unpack_from(">IQ", content, child_body + 20)
                else:
                    timescale, duration = struct.unpack_from(">II", content, child_body + 12)
                if timescale:
                    duration_seconds = duration / timescale
            elif child == b"trak":
                for item, item_body, item_end in _boxes(content, child_body, child_end):
                    if item == b"tkhd" and item_end - item_body >= 84:
                        width, height = struct.unpack_from(">II", content, item_end - 8)
                        width, height = width >> 16, height >> 16
                        if width and height and ratio is None:
                            ratio = width / height
    if duration_seconds is not None and duration_seconds < MIN_REEL_SECONDS:
        return "O vídeo tem menos de 3 segundos; o Instagram exige no mínimo 3s para Reels."
    if duration_seconds is not None and duration_seconds > MAX_REEL_SECONDS:
        return "O vídeo tem mais de 15 minutos; o Instagram aceita no máximo 15 min em Reels."
    if ratio is not None and not MIN_ASPECT_RATIO <= ratio <= MAX_ASPECT_RATIO:
        return "A proporção do vídeo não é aceita pelo Instagram para Reels."
    return None
