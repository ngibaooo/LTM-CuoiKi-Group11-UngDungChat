import base64
from io import BytesIO
from PIL import Image
from pathlib import Path
from typing import Tuple

from config import MAX_IMAGE_EDGE

class Media:
    @staticmethod
    def load_and_resize_to_b64(path: Path) -> Tuple[str, Tuple[int, int]]:
        img = Image.open(path)
        img = img.convert("RGB")
        w, h = img.size
        scale = 1.0
        m = max(w, h)
        if m > MAX_IMAGE_EDGE:
            scale = MAX_IMAGE_EDGE / m
            img = img.resize((int(w*scale), int(h*scale)))
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=85)
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        return b64, img.size

    @staticmethod
    def b64_to_photoimage(b64: str):
        import base64 as _b
        from PIL import Image, ImageTk
        from io import BytesIO
        data = _b.b64decode(b64)
        img = Image.open(BytesIO(data))
        return ImageTk.PhotoImage(img)