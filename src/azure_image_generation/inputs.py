from dataclasses import dataclass
import hashlib
from io import BytesIO
from pathlib import Path
import stat

from PIL import Image


@dataclass(frozen=True)
class InputImage:
    data: bytes
    mime_type: str
    upload_name: str
    width: int
    height: int

    def evidence(self):
        return {"upload_name": self.upload_name, "mime_type": self.mime_type,
                "width": self.width, "height": self.height, "bytes": len(self.data),
                "sha256": hashlib.sha256(self.data).hexdigest()}


def load_input_images(paths):
    paths = list(paths or ())
    if len(paths) > 16:
        raise ValueError("Provide at most 16 input images")
    images = []
    formats = {"PNG": ("image/png", "png"), "JPEG": ("image/jpeg", "jpg"),
               "WEBP": ("image/webp", "webp")}
    for index, path in enumerate(paths, start=1):
        path = Path(path).expanduser()
        info = path.stat()
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("Input images must be local regular files")
        if info.st_size >= 50_000_000:
            raise ValueError("Each input image must be smaller than 50 MB")
        data = path.read_bytes()
        if len(data) >= 50_000_000:
            raise ValueError("Each input image must be smaller than 50 MB")
        with Image.open(BytesIO(data)) as image:
            if image.format not in formats or getattr(image, "n_frames", 1) != 1:
                raise ValueError("Provide single-frame PNG, JPEG or WebP input images")
            mime_type, extension = formats[image.format]
            width, height = image.size
            image.verify()
        with Image.open(BytesIO(data)) as image:
            image.load()
        images.append(InputImage(data, mime_type, f"reference-{index:02}.{extension}", width, height))
    return tuple(images)
