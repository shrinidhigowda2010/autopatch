"""Turn any upload into plain source files.

Code and text files pass straight through. PDFs, Word documents and notebooks
are converted to code files, and images are read by Gemini vision. Archives are
not handled here; files.extract_zip and files.extract_tar unpack them.
"""

from __future__ import annotations

import io
import json
import logging
import re
import textwrap
import zipfile
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from xml.etree import ElementTree

from app.ingest.files import IngestError
from app.ingest.languages import (
    LANGUAGES,
    TEXT_NAMES,
    extension_for,
    guess_language,
    language_for,
)

log = logging.getLogger(__name__)

ARCHIVE_SUFFIXES = (".zip", ".tar", ".tar.gz", ".tgz")
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}
MAX_PDF_PAGES = 60
MAX_TEXT_CHARS = 1_000_000
MAX_DOCX_XML = 20 * 1024 * 1024

UNSUPPORTED = (
    "FixPilot can't read {what} yet. Upload source code, a zip/tar archive, a PDF, "
    "a Word document, a notebook, or a screenshot of code."
)


@dataclass
class ExtractedFile:
    path: str
    content: str
    language: str

    def as_dict(self) -> dict:
        return {"path": self.path, "content": self.content, "language": self.language}


@dataclass
class Extraction:
    kind: str  # code | pdf | image | notebook | docx
    files: list[ExtractedFile]
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "kind": self.kind,
            "files": [item.as_dict() for item in self.files],
            "notes": self.notes,
        }


# ---------------------------------------------------------------- sniffing


def sniff(data: bytes) -> str:
    """Name the format from the first bytes, ignoring what the filename claims."""
    head = data[:16]
    if head.startswith(b"%PDF"):
        return "pdf"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if head[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if head.startswith((b"PK\x03\x04", b"PK\x05\x06")):
        return "zip"
    if head.startswith(b"\x1f\x8b"):
        return "gzip"
    if data[257:262] == b"ustar":
        return "tar"
    if head[:2] == b"BM" and len(data) > 26 and decode_text(data) is None:
        return "image/bmp"
    if decode_text(data) is not None:
        return "text"
    return "binary"


def decode_text(data: bytes) -> str | None:
    """Return the text if the bytes are readable text, else None."""
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            return data.decode("utf-16")
        except UnicodeDecodeError:
            return None
    if b"\x00" in data[:8192]:
        return None
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            text = data.decode(encoding)
        except UnicodeDecodeError:
            continue
        controls = sum(1 for ch in text[:8192] if ord(ch) < 32 and ch not in "\r\n\t\f")
        if controls <= max(2, len(text[:8192]) // 100):
            return text
    return None


def is_archive(filename: str, data: bytes) -> bool:
    lowered = filename.lower()
    kind = sniff(data)
    if lowered.endswith(".docx"):
        return False
    return kind in {"zip", "gzip", "tar"} or lowered.endswith(ARCHIVE_SUFFIXES)


# ---------------------------------------------------------------- dispatch


def extract_upload(filename: str, data: bytes) -> Extraction:
    """Convert one non-archive upload into source files for the preview step."""
    name = PurePosixPath(filename.replace("\\", "/")).name or "upload"
    suffix = PurePosixPath(name.lower()).suffix
    kind = sniff(data)

    if suffix in IMAGE_SUFFIXES and not kind.startswith("image/"):
        raise IngestError(f"{name} is named like an image but isn't one.", 415)
    if suffix == ".pdf" and kind != "pdf":
        raise IngestError(f"{name} is named like a PDF but isn't one.", 415)

    if kind == "pdf":
        return _from_pdf(name, data)
    if kind.startswith("image/"):
        return _from_image(name, data, kind)
    if kind == "zip" and suffix == ".docx":
        return _from_docx(name, data)
    if kind == "text":
        text = decode_text(data) or ""
        if suffix == ".ipynb":
            return _from_notebook(name, text)
        return _from_text(name, text)
    if kind in {"zip", "gzip", "tar"}:
        raise IngestError("Archives are unpacked on upload, not in the preview.", 400)
    what = f"{suffix} files" if suffix else "that kind of file"
    raise IngestError(UNSUPPORTED.format(what=what), 415)


def _from_text(name: str, text: str) -> Extraction:
    if suffix_known(name):
        language = language_for(name)
    else:
        language = guess_language(text)
    return Extraction(kind="code", files=[ExtractedFile(name, _clip(text), language)])


def suffix_known(name: str) -> bool:
    lowered = name.lower()
    return PurePosixPath(lowered).suffix in LANGUAGES or lowered in TEXT_NAMES or lowered.startswith(".env")


# ---------------------------------------------------------------- PDF


def _from_pdf(name: str, data: bytes) -> Extraction:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted and not reader.decrypt(""):
            raise IngestError("That PDF is password-protected. Remove the password and try again.", 400)
        pages = list(reader.pages[:MAX_PDF_PAGES])
    except IngestError:
        raise
    except (PdfReadError, ValueError, KeyError, OSError) as exc:
        raise IngestError("That PDF could not be read.") from exc

    notes = [f"Read {len(pages)} page(s) of the PDF."]
    if len(reader.pages) > MAX_PDF_PAGES:
        notes.append(f"Only the first {MAX_PDF_PAGES} pages were read.")
    texts = [_page_text(page) for page in pages]
    text = "\n".join(texts).strip()
    stem = PurePosixPath(name).stem or "document"

    if not text:
        # A scanned PDF: no text layer, so read the page images instead.
        images = _pdf_images(pages, limit=3)
        if not images:
            raise IngestError("That PDF has no text or images FixPilot can read.", 422)
        files: list[ExtractedFile] = []
        for index, (image_name, image_data) in enumerate(images, start=1):
            result = _from_image(f"{stem}_page{index}{PurePosixPath(image_name).suffix or '.png'}", image_data, sniff(image_data))
            files.extend(result.files)
        notes.append("The PDF is scanned, so the code was read from the page images.")
        return Extraction(kind="pdf", files=files, notes=notes)

    files = [ExtractedFile(path, content, guess_language(content)) for path, content in split_code_blocks(text, stem)]
    if all(item.language == "Text" for item in files):
        notes.append("No obvious code found. Check the preview and edit it before scanning.")
    return Extraction(kind="pdf", files=files, notes=notes)


def _page_text(page) -> str:
    """Plain extraction keeps real spaces; layout mode rebuilds indentation when plain lost it."""
    plain = _safe_extract(page)
    if any(line.startswith((" ", "\t")) and line.strip() for line in plain.splitlines()):
        return plain
    layout = _safe_extract(page, extraction_mode="layout")
    if not layout.strip():
        return plain
    # Layout mode sometimes pads a line with the page's horizontal offset; drop those runs.
    lines = [line.lstrip() if len(line) - len(line.lstrip()) > 60 else line for line in layout.splitlines()]
    return "\n".join(lines)


def _safe_extract(page, **options) -> str:
    try:
        return page.extract_text(**options) or ""
    except Exception:  # noqa: BLE001 - odd PDFs; treat as no text on this page
        return ""


def _pdf_images(pages, limit: int) -> list[tuple[str, bytes]]:
    found: list[tuple[str, bytes]] = []
    for page in pages:
        try:
            for image in page.images:
                found.append((image.name, image.data))
                if len(found) >= limit:
                    return found
        except Exception:  # noqa: BLE001 - broken image streams are skipped
            continue
    return found


# ---------------------------------------------------------------- code blocks

_CODE_START = re.compile(
    r"^\s*(def|class|import|from|return|if|elif|else|for|while|try|except|finally|with|print|"
    r"public|private|protected|static|void|int|float|double|char|bool|string|const|let|var|"
    r"function|#include|using|package|func|fn|struct|select|insert|update|create|echo|end)\b",
    re.IGNORECASE,
)
_CODE_MARK = re.compile(r"[{};]\s*$|^\s*(#|//|/\*|\*/|@\w)|\w\(.*\)|\s=\s|==|!=|<=|>=|\+=|->|=>|\[\d*\]")


def _line_kind(line: str) -> str:
    stripped = line.strip()
    if not stripped:
        return "blank"
    words = stripped.split()
    looks_code = bool(_CODE_START.match(stripped) or _CODE_MARK.search(stripped) or line.startswith(("    ", "\t")))
    if len(words) >= 7 and not re.search(r"[=(){}\[\];]", stripped):
        return "prose"
    return "code" if looks_code else "prose"


def split_code_blocks(text: str, stem: str) -> list[tuple[str, str]]:
    """Pull code out of document text: one file if it is all code, else one file per block."""
    lines = text.replace("\r\n", "\n").split("\n")
    kinds = [_line_kind(line) for line in lines]
    filled = [kind for kind in kinds if kind != "blank"]
    if not filled:
        return [(f"{stem}.txt", "")]
    code_share = filled.count("code") / len(filled)
    if code_share >= 0.9:
        content = _tidy("\n".join(lines))
        return [(f"{stem}{extension_for(guess_language(content))}", content)]

    blocks: list[list[str]] = []
    current: list[str] = []
    for line, kind in zip(lines, kinds):
        if kind == "prose":
            if current:
                blocks.append(current)
            current = []
        elif kind == "code" or current:
            current.append(line)
    if current:
        blocks.append(current)
    blocks = [block for block in blocks if sum(1 for line in block if line.strip()) >= 2]
    if not blocks:
        return [(f"{stem}.txt", _tidy(text))]

    results = []
    for index, block in enumerate(blocks, start=1):
        content = _tidy("\n".join(block))
        name = stem if len(blocks) == 1 else f"{stem}_{index}"
        results.append((f"{name}{extension_for(guess_language(content))}", content))
    return results


def _tidy(text: str) -> str:
    lines = [line.rstrip() for line in text.split("\n")]
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    # Layout extraction pads blank runs; keep at most two blank lines in a row.
    collapsed: list[str] = []
    for line in lines:
        if not line and len(collapsed) >= 2 and not collapsed[-1] and not collapsed[-2]:
            continue
        collapsed.append(line)
    return _clip(textwrap.dedent("\n".join(collapsed)) + "\n")


def _clip(text: str) -> str:
    return text[:MAX_TEXT_CHARS]


# ---------------------------------------------------------------- images


def _from_image(name: str, data: bytes, kind: str) -> Extraction:
    from app.llm.gemini import GeminiError, read_code_from_image

    mime, payload = _image_for_model(data, kind)
    stem = PurePosixPath(name).stem or "screenshot"
    try:
        result = read_code_from_image(payload, mime)
        engine_note = "Code read from the image by Gemini vision. Check it before scanning."
    except GeminiError as exc:
        log.info("gemini vision unavailable: %s", exc)
        result = _ocr(payload)
        if result is None:
            raise IngestError(
                "Reading code from images needs the AI engine, which is offline right now. "
                "Paste the code as text instead.",
                503,
            ) from exc
        engine_note = "Code read with OCR (the AI engine is offline). Check spacing before scanning."

    code = (result.get("code") or "").replace("\r\n", "\n")
    if not code.strip():
        raise IngestError("FixPilot couldn't find any code in that image.", 422)
    language = guess_language(code)
    filename = PurePosixPath(str(result.get("filename") or "")).name
    if not filename or not suffix_known(filename):
        filename = f"{stem}{extension_for(language)}"
    else:
        language = language_for(filename)
    return Extraction(kind="image", files=[ExtractedFile(filename, _tidy(code), language)], notes=[engine_note])


def _image_for_model(data: bytes, kind: str) -> tuple[str, bytes]:
    """Check the image really decodes, and turn GIF/BMP into PNG for Gemini."""
    from PIL import Image, UnidentifiedImageError

    try:
        with Image.open(io.BytesIO(data)) as image:
            image.verify()
        if kind in {"image/png", "image/jpeg", "image/webp"}:
            return kind, data
        with Image.open(io.BytesIO(data)) as image:
            image.seek(0)
            out = io.BytesIO()
            image.convert("RGB").save(out, format="PNG")
            return "image/png", out.getvalue()
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError) as exc:
        raise IngestError("That image could not be opened.", 415) from exc


def _ocr(data: bytes) -> dict | None:
    """Optional Tesseract fallback, used only when it is installed."""
    try:
        import shutil

        import pytesseract  # type: ignore[import-not-found]
        from PIL import Image

        if not shutil.which("tesseract"):
            return None
        with Image.open(io.BytesIO(data)) as image:
            text = pytesseract.image_to_string(image)
    except Exception:  # noqa: BLE001 - OCR is best effort
        return None
    return {"code": text}


# ---------------------------------------------------------------- notebooks and Word


def _from_notebook(name: str, text: str) -> Extraction:
    try:
        notebook = json.loads(text)
    except json.JSONDecodeError as exc:
        raise IngestError("That notebook is not valid JSON.") from exc
    cells = notebook.get("cells") if isinstance(notebook, dict) else None
    if not isinstance(cells, list):
        raise IngestError("That notebook has no cells FixPilot can read.")
    language = (
        ((notebook.get("metadata") or {}).get("kernelspec") or {}).get("language")
        or ((notebook.get("metadata") or {}).get("language_info") or {}).get("name")
        or "python"
    )
    parts = []
    for index, cell in enumerate(cells, start=1):
        if not isinstance(cell, dict) or cell.get("cell_type") != "code":
            continue
        source = cell.get("source", "")
        source = "".join(source) if isinstance(source, list) else str(source)
        if not source.strip():
            continue
        # Shell commands and magics are not Python; keep them visible as comments.
        lines = [f"# {line}" if line.lstrip().startswith(("!", "%")) else line for line in source.splitlines()]
        parts.append(f"# %% cell {index}\n" + "\n".join(lines))
    if not parts:
        raise IngestError("That notebook has no code cells.", 422)
    pretty = str(language).strip().lower()
    label = {"python": "Python", "r": "R", "julia": "Julia", "javascript": "JavaScript"}.get(pretty, "Python")
    suffix = {"Python": ".py", "R": ".r", "Julia": ".jl", "JavaScript": ".js"}[label]
    stem = PurePosixPath(name).stem or "notebook"
    content = "\n\n".join(parts) + "\n"
    return Extraction(
        kind="notebook",
        files=[ExtractedFile(f"{stem}{suffix}", _clip(content), label)],
        notes=[f"Joined {len(parts)} code cell(s) into one file. Markdown cells were left out."],
    )


_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _from_docx(name: str, data: bytes) -> Extraction:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            info = archive.getinfo("word/document.xml")
            if info.file_size > MAX_DOCX_XML:
                raise IngestError("That Word document is too large to read.")
            root = ElementTree.fromstring(archive.read(info))
    except IngestError:
        raise
    except (KeyError, zipfile.BadZipFile, ElementTree.ParseError) as exc:
        raise IngestError("That Word document could not be read.") from exc

    paragraphs = []
    for paragraph in root.iter(f"{_W}p"):
        pieces = []
        for node in paragraph.iter():
            if node.tag == f"{_W}t" and node.text:
                pieces.append(node.text)
            elif node.tag == f"{_W}tab":
                pieces.append("\t")
            elif node.tag in {f"{_W}br", f"{_W}cr"}:
                pieces.append("\n")
        paragraphs.append("".join(pieces).replace("\t", "    "))
    text = "\n".join(paragraphs).strip()
    if not text:
        raise IngestError("That Word document has no text.", 422)
    stem = PurePosixPath(name).stem or "document"
    files = [ExtractedFile(path, content, guess_language(content)) for path, content in split_code_blocks(text, stem)]
    return Extraction(kind="docx", files=files, notes=["Text read from the Word document."])
