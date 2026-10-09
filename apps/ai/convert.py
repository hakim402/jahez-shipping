"""stdin file -> bounded text and JPEG pages; never open URLs or retain render files."""
import base64
import io
import json
import math
import sys
from apps.shipments.inspect_file import inspect_bytes


def jpeg(image):
    image = image.convert('RGB')
    image.thumbnail((1400, 1400))
    output = io.BytesIO()
    image.save(output, 'JPEG', quality=80)
    if output.tell() > 650000:
        raise ValueError('image limit')
    return base64.b64encode(output.getvalue()).decode('ascii')


def convert(data):
    if not 0 < len(data) <= 5 * 1024 * 1024:
        raise ValueError('size limit')
    meta = inspect_bytes(data)
    if meta['pages'] > 5:
        raise ValueError('AI supports at most five pages; split or process manually')
    records, images = [], []
    if meta['mime'] == 'application/pdf':
        from pypdf import PdfReader
        import pypdfium2 as pdfium
        pdf = PdfReader(io.BytesIO(data), strict=True)
        rendered = None
        try:
            for i, page in enumerate(pdf.pages):
                text = page.extract_text() or ''
                if len(text) > 10000:
                    raise ValueError('page text limit')
                scanned = len(text.strip()) < 40
                record = {'id': f'page:{i+1}', 'page': i+1, 'text': text, 'scanned': scanned}
                records.append(record)
                if scanned:
                    rendered = rendered or pdfium.PdfDocument(data)
                    p = rendered[i]
                    w, h = p.get_size()
                    if not 1 <= w <= 20000 or not 1 <= h <= 20000:
                        raise ValueError('page dimensions')
                    scale = min(2.0, 1400 / max(w, h), math.sqrt(1500000 / (w*h)))
                    bitmap = p.render(scale=scale)
                    image = bitmap.to_pil()
                    images.append({'id': record['id'], 'jpeg': jpeg(image)})
                    image.close(); bitmap.close(); p.close()
        finally:
            if rendered is not None:
                rendered.close()
    else:
        from PIL import Image
        with Image.open(io.BytesIO(data)) as image:
            images.append({'id': 'page:1', 'jpeg': jpeg(image)})
        records.append({'id': 'page:1', 'page': 1, 'text': '', 'scanned': True})
    if sum(len(r['text']) for r in records) > 24000:
        raise ValueError('document text limit')
    return {'records': records, 'images': images, 'warnings': ['Scanned pages need visual source verification.'] if images else []}


if __name__ == '__main__':
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_CPU, (10, 10))
        resource.setrlimit(resource.RLIMIT_AS, (768 * 1024 * 1024, 768 * 1024 * 1024))
        print(json.dumps(convert(sys.stdin.buffer.read(5 * 1024 * 1024 + 1)), ensure_ascii=False))
    except Exception:
        print(json.dumps({'error': 'Document conversion rejected.'}))
        sys.exit(1)
