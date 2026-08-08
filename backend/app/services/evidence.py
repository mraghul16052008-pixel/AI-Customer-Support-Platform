from pathlib import Path

MAX_EVIDENCE_BYTES = 4 * 1024 * 1024
MAX_EVIDENCE_PER_CONVERSATION = 3
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}


def safe_filename(value: str | None) -> str:
    name = Path(value or "support-image").name.strip()
    return (name or "support-image")[:120]


def validate_image(content: bytes, declared_type: str | None) -> str:
    if not content:
        raise ValueError("The uploaded image is empty.")
    if len(content) > MAX_EVIDENCE_BYTES:
        raise ValueError("The uploaded image exceeds the 4 MB limit.")
    detected = None
    if content.startswith(b"\xff\xd8\xff"):
        detected = "image/jpeg"
    elif content.startswith(b"\x89PNG\r\n\x1a\n"):
        detected = "image/png"
    elif len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        detected = "image/webp"
    if detected is None or declared_type not in ALLOWED_IMAGE_TYPES or detected != declared_type:
        raise ValueError("Only valid JPEG, PNG, or WebP images are accepted.")
    return detected
