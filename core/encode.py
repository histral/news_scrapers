import zlib
import base64
import logging as Logger

Logger.basicConfig(
    level=Logger.INFO,
    format="[%(levelname)s] (%(asctime)s) -> %(message)s",
    handlers=[
        Logger.StreamHandler(),
    ],
)


def compress_string(s: str) -> str:
    """
    Compress and Encode [s] using `zlib` and `base64`
    """
    try:
        compressed = zlib.compress(s.encode())
        return base64.b64encode(compressed).decode()
    except Exception as e:
        Logger.error(f"ERROR: Unable to compress text: {e}")
        return s
