"""
Delphi source chunker — splits .pas files into semantic chunks

No dependency on ZVec or any other external library; pure text processing.
Input: .pas file path
Output: list of chunk dicts

Chunk strategy:
  - class / record / interface / object → standalone structural chunk (with the complete body)
  - everything else (const, type alias, enum, function, etc.) → one file-level fallback chunk
"""

import re
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from src.utils.file_backup import detect_encoding

logger = logging.getLogger(__name__)

# ── Constants ──
STRUCTURED_TYPES = {'class', 'record', 'interface', 'object'}
"""Types that get their own structural chunk"""


def _sanitize_unicode(text: str) -> str:
    """Remove lone surrogates that cannot be encoded as UTF-8.

    When a source file's encoding is misdetected (e.g. truncated UTF-16, mixed encodings),
    the text read in may contain lone surrogates (U+D800–U+DFFF). Such characters cannot be
    encoded as UTF-8, and Doc.insert on Rust-bound collections such as zvec raises
    ``expected STRING, got str``, crashing the index. They are replaced here with U+FFFD
    (the replacement character), so the chunk output is always safely encodable.

    Args:
        text: the original text

    Returns:
        The cleaned text (UTF-8 encodable)
    """
    try:
        text.encode('utf-8')
        return text
    except UnicodeEncodeError:
        return text.encode('utf-8', errors='replace').decode('utf-8')


# ═══════════════════════════════════════════
# Text preprocessing
# ═══════════════════════════════════════════

def _strip_comments(text: str) -> str:
    """Remove Delphi comments, leaving the line structure unchanged"""
    # Brace comments { ... }
    text = re.sub(r'\{[^}]*\}', ' ', text)
    # Star-paren comments (* ... *)
    text = re.sub(r'\(\*[^*]*\*\)', ' ', text)
    # Double-slash comments // (must skip // inside strings)
    lines = text.split('\n')
    result = []
    for line in lines:
        in_string = False
        for i, c in enumerate(line):
            if c == "'" and (i == 0 or line[i - 1] != '\\'):
                in_string = not in_string
            elif c == '/' and i + 1 < len(line) and line[i + 1] == '/' and not in_string:
                line = line[:i] + ' '
                break
        result.append(line)
    return '\n'.join(result)


# ── Declaration regexes (one line each) ──
_RE_CLASS_DECL = re.compile(
    r'^\s*(\w[\w.]*)\s*=\s*'
    r'(class|record|interface|object)\s*'
    r'(?:\(\s*([\w.,\s]+?)\s*\))?'      # base class (optional)
    r'(?:\s+class\s+)?'                  # class helper / class of
    r'(?:of\s+\w[\w.]*)?'                # enum base type
    r'(?:\s*;)?',
    re.IGNORECASE
)

_RE_UNIT = re.compile(r'^\s*unit\s+(\w+(?:\.\w+)*)\s*;')
_RE_USES = re.compile(r'uses\s+(.+?);', re.IGNORECASE | re.DOTALL)
_RE_USES_IN = re.compile(r'\s+in\s+[\'"][^\'"]+[\'"]')


# ═══════════════════════════════════════════
# Core chunker
# ═══════════════════════════════════════════

def chunk_delphi_file(file_path: str) -> List[Dict]:
    """
    Split a single .pas file into semantic chunks.

    Args:
        file_path: .pas file path

    Returns:
        A list of chunk dicts, each chunk containing:
          - entity_name: entity name
          - chunk_type: class/record/interface/object/unit
          - base_class: base class name (structural chunks only)
          - unit_name: unit name
          - uses_list: uses list
          - chunk_text: code text
          - start_line: start line number (1-indexed)
          - end_line: end line number
          - file_path: original file path
    """
    # ── Read the file (encoding detected automatically) ──
    try:
        enc = detect_encoding(file_path)
        with open(file_path, 'r', encoding=enc, errors='replace') as f:
            raw_text = f.read()
    except Exception as e:
        logger.warning(f"Failed to read file: {file_path}: {e}")
        return []

    # Clean up lone surrogates an encoding misdetection may have introduced, to prevent downstream zvec insert crashes
    raw_text = _sanitize_unicode(raw_text)

    lines = raw_text.split('\n')
    text = _strip_comments(raw_text)
    tlines = text.split('\n')

    # ── Extract the unit name ──
    unit_name = ''
    for line in tlines:
        m = _RE_UNIT.match(line)
        if m:
            unit_name = m.group(1)
            break

    # ── Extract the uses list ──
    uses_list: List[str] = []
    in_uses = False
    ubuf = ''
    for line in tlines:
        if re.match(r'^\s*uses\s+', line, re.IGNORECASE):
            in_uses = True
            ubuf = line
        elif in_uses:
            ubuf += ' ' + line
            if ';' in line:
                u = _RE_USES.search(ubuf)
                if u:
                    for p in u.group(1).split(','):
                        p = p.strip()
                        # strip the 'in filename' part
                        p = p.split()[0] if p.split() else p
                        if p and not p.startswith('//'):
                            uses_list.append(p)
                in_uses = False
                ubuf = ''

    # ── Parse the type section ──
    chunks: List[Dict] = []
    section: Optional[str] = None  # 'interface' | 'implementation' | None
    type_start = -1  # line where the 'type' keyword appears

    i = 0
    while i < len(tlines):
        s = tlines[i].strip()

        # Section markers
        if re.match(r'^\s*interface\s*$', s, re.IGNORECASE) and section is None:
            section = 'interface'
            i += 1
            continue
        if re.match(r'^\s*implementation\s*$', s, re.IGNORECASE) and section == 'interface':
            section = 'implementation'
            i += 1
            continue

        # Inside the interface section: recognise type/var/const boundaries
        if section == 'interface' and type_start < 0:
            if re.match(r'^\s*type\s*$', s, re.IGNORECASE):
                type_start = i
                i += 1
                continue
            if re.match(r'^\s*(var|const|resourcestring|threadvar)\s*$', s, re.IGNORECASE):
                i += 1
                continue

        # Inside the type section: recognise structural declarations
        if type_start >= 0 and i >= type_start:
            m = _RE_CLASS_DECL.match(s)
            if m:
                name = m.group(1)
                kind = m.group(2).lower()
                base = (m.group(3) or '').split(',')[0].strip()

                # Capture the body (tracking begin/end depth)
                body: List[str] = []
                depth = 0
                j = i
                while j < len(tlines):
                    body.append(lines[j])  # use the original text to preserve formatting
                    tl = tlines[j].strip()
                    if tl.startswith('begin'):
                        depth += 1
                    elif tl.startswith('end'):
                        if depth > 0:
                            depth -= 1
                        elif tl.rstrip().endswith(';'):
                            j += 1
                            break
                    j += 1

                chunks.append({
                    'entity_name': name,
                    'chunk_type': kind,
                    'base_class': base,
                    'unit_name': unit_name,
                    'uses_list': uses_list,
                    'chunk_text': '\n'.join(body),
                    'start_line': i + 1,
                    'end_line': j + 1,
                    'file_path': str(Path(file_path).as_posix()),
                })
                i = j
                continue

        i += 1

    # ── Fallback: build a file-level chunk when no structural chunk exists ──
    if not chunks:
        name = unit_name or Path(file_path).stem
        chunks.append({
            'entity_name': name,
            'chunk_type': 'unit',
            'base_class': '',
            'unit_name': unit_name,
            'uses_list': uses_list,
            'chunk_text': raw_text,
            'start_line': 1,
            'end_line': len(lines),
            'file_path': str(Path(file_path).as_posix()),
        })

    return chunks


def chunk_directory(source_dir: str,
                    extensions: set = None,
                    progress_callback=None) -> List[Dict]:
    """
    Chunk all source files under a directory in batch.

    Args:
        source_dir: source directory
        extensions: set of file extensions (default {'.pas'})
        progress_callback: progress callback (percent, message, extra_dict)

    Returns:
        A list of all chunks
    """
    if extensions is None:
        extensions = {'.pas'}

    src = Path(source_dir)
    files = sorted(src.rglob('*'))
    files = [f for f in files if f.is_file() and f.suffix.lower() in extensions]

    all_chunks: List[Dict] = []
    for i, f in enumerate(files):
        try:
            chunks = chunk_delphi_file(str(f))
            all_chunks.extend(chunks)
        except Exception as e:
            logger.warning(f"Chunking failed: {f}: {e}")

        if progress_callback and (i + 1) % 100 == 0:
            pct = ((i + 1) / len(files) * 100) if files else 0
            progress_callback(pct, f.name, {"current": i + 1, "total": len(files)})

    return all_chunks


def chunk_file_list(file_paths: List[str],
                    progress_callback=None) -> List[Dict]:
    """
    Chunk a list of files in batch.

    Args:
        file_paths: list of file paths
        progress_callback: progress callback (percent, message, extra_dict)

    Returns:
        A list of all chunks
    """
    all_chunks: List[Dict] = []
    for i, fp in enumerate(file_paths):
        try:
            chunks = chunk_delphi_file(fp)
            all_chunks.extend(chunks)
        except Exception as e:
            logger.warning(f"Chunking failed: {fp}: {e}")

        if progress_callback and (i + 1) % 100 == 0:
            pct = ((i + 1) / len(file_paths) * 100) if file_paths else 0
            progress_callback(pct, Path(fp).name, {"current": i + 1, "total": len(file_paths)})

    return all_chunks
