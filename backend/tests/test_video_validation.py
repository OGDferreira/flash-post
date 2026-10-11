import struct

from app.instagram.video_validation import validate_reel_video


def _box(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I4s", len(payload) + 8, kind) + payload


def _mp4(duration_seconds: int, width: int, height: int) -> bytes:
    mvhd = _box(
        b"mvhd",
        bytes(4) + bytes(8) + struct.pack(">II", 1000, duration_seconds * 1000) + bytes(80),
    )
    tkhd_payload = bytes(76) + struct.pack(">II", width << 16, height << 16)
    trak = _box(b"trak", _box(b"tkhd", tkhd_payload))
    ftyp = _box(b"ftyp", b"isom" + bytes(8))
    return ftyp + _box(b"moov", mvhd + trak)


def test_valid_reel_passes():
    assert validate_reel_video(_mp4(10, 1080, 1920)) is None


def test_too_short_reel_is_rejected():
    assert "3 segundos" in (validate_reel_video(_mp4(1, 1080, 1920)) or "")


def test_too_long_reel_is_rejected():
    assert "15 minutos" in (validate_reel_video(_mp4(1000, 1080, 1920)) or "")


def test_unparseable_video_is_not_blocked():
    assert validate_reel_video(b"\x00\x00\x00\x18ftypisom" + bytes(40)) is None
