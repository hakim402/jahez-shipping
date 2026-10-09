"""Bounded subprocess file inspection; no remote resources or rendering."""
import io
import json
import sys
import warnings


def inspect_bytes(data):
    if data.startswith(b"%PDF-"):
        from pypdf import PdfReader
        from pypdf.generic import DictionaryObject, ArrayObject, IndirectObject
        reader = PdfReader(io.BytesIO(data), strict=True)
        if reader.is_encrypted:
            raise ValueError("Encrypted PDFs are not supported.")
        pages = len(reader.pages)
        if not 1 <= pages <= 40:
            raise ValueError("A PDF must contain 1–40 pages.")
        seen = set()
        stack = [reader.trailer]
        nodes = 0
        forbidden = {"/JavaScript", "/JS", "/OpenAction", "/AA", "/Launch", "/EmbeddedFiles", "/XFA", "/RichMedia", "/URI", "/SubmitForm", "/GoToR"}
        while stack:
            obj = stack.pop()
            if isinstance(obj, IndirectObject):
                key = (obj.idnum, obj.generation)
                if key in seen:
                    continue
                seen.add(key)
                obj = obj.get_object()
            nodes += 1
            if nodes > 30000:
                raise ValueError("PDF object limit exceeded.")
            if isinstance(obj, DictionaryObject):
                if forbidden.intersection(obj.keys()) or str(obj.get("/S", "")) in forbidden:
                    raise ValueError("PDF contains active content or external actions.")
                stack.extend(obj.values())
            elif isinstance(obj, ArrayObject):
                stack.extend(obj)
        return {"mime": "application/pdf", "extension": ".pdf", "pages": pages}
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = 20_000_000
    warnings.simplefilter("error", Image.DecompressionBombWarning)
    with Image.open(io.BytesIO(data)) as image:
        if image.format not in ("PNG", "JPEG") or getattr(image, "n_frames", 1) != 1:
            raise ValueError("Only single-frame PNG and JPEG images are supported.")
        image.verify()
        kind = image.format
    with Image.open(io.BytesIO(data)) as image:
        image.load()
    return {"mime": "image/png" if kind == "PNG" else "image/jpeg", "extension": ".png" if kind == "PNG" else ".jpg", "pages": 1}


if __name__ == "__main__":
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_CPU, (5, 5))
        resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
        print(json.dumps(inspect_bytes(sys.stdin.buffer.read(5 * 1024 * 1024 + 1))))
    except Exception:
        print(json.dumps({"error": "File inspection rejected the document."}))
        sys.exit(1)
