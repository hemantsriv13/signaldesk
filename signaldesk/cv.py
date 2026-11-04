"""Local CV text extraction. Import is a preview; saving needs a separate action."""
from io import BytesIO
from pathlib import Path
import re
from xml.etree import ElementTree
from zipfile import ZipFile, BadZipFile

MAX_BYTES = 5 * 1024 * 1024
MAX_TEXT = 60_000
MAX_FACTS = 30


def preview_cv(filename: str, payload: bytes) -> dict:
    if not payload or len(payload) > MAX_BYTES:
        raise ValueError('Choose a non-empty CV smaller than 5 MB.')
    ext = Path(filename).suffix.lower()
    warnings = []
    try:
        if ext == '.txt':
            text = payload.decode('utf-8-sig')
        elif ext == '.docx':
            with ZipFile(BytesIO(payload)) as archive:
                member = archive.getinfo('word/document.xml')
                if member.file_size > 8 * 1024 * 1024:
                    raise ValueError('The Word document is too large to extract. Export a plain-text CV.')
                root = ElementTree.fromstring(archive.read(member))
                ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
                text = '\n'.join(''.join(n.text or '' for n in p.findall('.//w:t', ns))
                                 for p in root.findall('.//w:p', ns))
        elif ext == '.pdf':
            from pypdf import PdfReader
            reader = PdfReader(BytesIO(payload))
            if reader.is_encrypted:
                raise ValueError('Export an unencrypted PDF or upload a DOCX/TXT CV.')
            if len(reader.pages) > 20:
                raise ValueError('Choose a CV with at most 20 pages.')
            parts = []
            for page in reader.pages:
                parts.append(page.extract_text() or '')
                if sum(map(len, parts)) > MAX_TEXT:
                    raise ValueError('The CV contains too much text. Upload a shorter CV.')
            text = '\n'.join(parts)
            warnings.append('PDF reading order can be imperfect. Check dates, columns and wrapped lines; edit facts before saving.')
        else:
            raise ValueError('Supported CV formats: PDF, DOCX and UTF-8 TXT.')
    except ValueError:
        raise
    except (UnicodeError, BadZipFile, KeyError, ElementTree.ParseError):
        raise ValueError('Could not read that CV. Export it as DOCX or UTF-8 TXT and try again.') from None
    except Exception:
        raise ValueError('Could not extract text from that CV. Try DOCX or TXT.') from None
    if len(text) > MAX_TEXT:
        raise ValueError('The CV contains too much text. Upload a shorter CV.')
    lines = [re.sub(r'\s+', ' ', line).strip(' •\t') for line in text.splitlines()]
    lines = list(dict.fromkeys(line for line in lines if line))
    if not lines or sum(map(len, lines)) < 30:
        raise ValueError('No usable CV text found. Scanned PDFs need OCR first; try DOCX or paste the text.')
    # Keep whole statements; do not silently cut qualifications or negate meaning.
    candidates = [line for line in lines if len(line) <= 400]
    if len(candidates) != len(lines):
        warnings.append('Some paragraphs exceed 400 characters. Split them into shorter factual statements in the extracted-text box.')
    if len(candidates) > 200:
        candidates = candidates[:200]
        warnings.append('Only the first 200 candidate lines are listed. The extracted text is available below.')
    warnings.append('Extraction does not verify claims. Select up to 30 relevant facts; remove contact details, headings and anything you do not claim.')
    return {'text': text, 'candidates': candidates, 'warnings': warnings,
            'filename': Path(filename.replace('\\', '/')).name, 'max_facts': MAX_FACTS}
