#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generic document scanner
Supports doc/docx/txt/md/html/pdf/epub/hlp/web pages and other document formats
"""

import re
import json
import os
import struct
import hashlib
import logging
import threading
import subprocess
import tempfile
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Callable
from concurrent.futures import ProcessPoolExecutor, as_completed
from multiprocessing import cpu_count

import zvec

from src.constants import (
    CHUNK_SIZE_DOCUMENT_LINES,
    POLL_INTERVAL_AUTOMATION,
    TIMEOUT_DOCUMENT_ARCHIVE_EXTRACT,
    TIMEOUT_DOCUMENT_ARCHIVE_LIST,
    TIMEOUT_DOCUMENT_CONVERT,
    TIMEOUT_DOCUMENT_WORKER_JOIN,
    TIMEOUT_DOCUMENT_WORKER_RESULT,
    TIMEOUT_NETWORK_REQUEST,
)

logger = logging.getLogger(__name__)

# Default excluded multilingual subdirectories
DEFAULT_EXCLUDE_DIRS = {'ja', 'fr', 'de', 'es', 'it', 'ko', 'pt', 'ru', 'zh'}

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

try:
    import html2text
except ImportError:
    html2text = None


class DocumentProcessor:
    """Document processor base class"""
    
    def __init__(self):
        self.supported_extensions = []
    
    def can_process(self, file_path: Path) -> bool:
        return file_path.suffix.lower() in self.supported_extensions
    
    def process(self, file_path: Path) -> Optional[Dict]:
        raise NotImplementedError


class TextProcessor(DocumentProcessor):
    """Plain text processor (.txt)"""
    
    def __init__(self):
        self.supported_extensions = ['.txt']
    
    def process(self, file_path: Path) -> Optional[Dict]:
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            lines = content.split('\n')
            title = lines[0].strip()[:100] if lines else file_path.stem
            
            return {
                'title': title,
                'content': content,
                'content_type': 'text',
                'size': len(content),
                'line_count': len(lines),
                'hash': hashlib.md5(content.encode()).hexdigest(),
                'sections': [],
                'code_examples': []
            }
        except Exception:
            return None


class MarkdownProcessor(DocumentProcessor):
    """Markdown processor (.md)"""
    
    def __init__(self):
        self.supported_extensions = ['.md', '.markdown']
    
    def process(self, file_path: Path) -> Optional[Dict]:
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            title = self._extract_title(content) or file_path.stem
            sections = self._extract_sections(content)
            code_examples = self._extract_code_blocks(content)
            
            return {
                'title': title,
                'content': content,
                'content_type': 'markdown',
                'size': len(content),
                'line_count': content.count('\n') + 1,
                'hash': hashlib.md5(content.encode()).hexdigest(),
                'sections': sections,
                'code_examples': code_examples
            }
        except Exception:
            return None
    
    def _extract_title(self, content: str) -> Optional[str]:
        for line in content.split('\n'):
            if line.startswith('#'):
                return line.lstrip('#').strip()[:100]
        return None
    
    def _extract_sections(self, content: str) -> List[Dict]:
        sections = []
        for line in content.split('\n'):
            if line.startswith('#'):
                level = len(line) - len(line.lstrip('#'))
                title = line.lstrip('#').strip()
                sections.append({'level': level, 'title': title})
        return sections
    
    def _extract_code_blocks(self, content: str) -> List[str]:
        pattern = re.compile(r'```[\w]*\n(.*?)```', re.DOTALL)
        return [m.group(1).strip() for m in pattern.finditer(content)]


class HTMLProcessor(DocumentProcessor):
    """HTML processor (.htm, .html) — converts with html2text, no BeautifulSoup needed"""
    
    def __init__(self):
        self.supported_extensions = ['.htm', '.html']
        self.converter = html2text.HTML2Text() if html2text else None
        if self.converter:
            self.converter.ignore_links = False
            self.converter.ignore_images = True
            self.converter.body_width = 0
    
    def process(self, file_path: Path) -> Optional[Dict]:
        if not self.converter:
            return None
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                html_content = f.read()
            
            # Extract <title> with regex (first match is enough)
            title_match = re.search(r'<title[^>]*>(.*?)</title>', html_content, re.IGNORECASE | re.DOTALL)
            title = title_match.group(1).strip() if title_match else Path(file_path).stem
            
            # html2text converts HTML to Markdown (skips script/style automatically)
            markdown = self.converter.handle(html_content)
            
            hash_val = hashlib.md5(markdown.encode()).hexdigest()
            
            return {
                'title': title,
                'content': markdown,
                'content_type': 'html',
                'size': len(markdown),
                'line_count': markdown.count('\n') + 1,
                'hash': hash_val,
                'sections': [],
                'code_examples': []
            }
        except Exception:
            return None


class DocxProcessor(DocumentProcessor):
    """Word document processor (.docx)"""
    
    def __init__(self):
        self.supported_extensions = ['.docx']
        self.has_docx = self._check_docx()
    
    def _check_docx(self) -> bool:
        try:
            from docx import Document
            return True
        except ImportError:
            return False
    
    def process(self, file_path: Path) -> Optional[Dict]:
        if not self.has_docx:
            return {
                'title': file_path.stem,
                'content': f"Word .docx processing requires installing dependencies:\n"
                          f"  pip install python-docx",
                'content_type': 'docx',
                'size': 0,
                'line_count': 0,
                'hash': '',
                'sections': [],
                'code_examples': [],
                'requires_dependencies': True,
                'install_hint': 'pip install python-docx'
            }
        
        try:
            from docx import Document
            doc = Document(str(file_path))
            
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            content = '\n'.join(paragraphs)
            
            title = paragraphs[0][:100] if paragraphs else file_path.stem
            sections = self._extract_sections(doc)
            code_examples = self._extract_code_examples(paragraphs)
            
            return {
                'title': title,
                'content': content,
                'content_type': 'docx',
                'size': len(content),
                'line_count': len(paragraphs),
                'hash': hashlib.md5(content.encode()).hexdigest(),
                'sections': sections,
                'code_examples': code_examples
            }
        except Exception:
            return None
    
    def _extract_sections(self, doc) -> List[Dict]:
        sections = []
        for p in doc.paragraphs:
            if p.style.name.startswith('Heading'):
                try:
                    level = int(p.style.name.split()[-1])
                except (ValueError, IndexError):
                    level = 1
                sections.append({'level': level, 'title': p.text})
        return sections
    
    def _extract_code_examples(self, paragraphs: List[str]) -> List[str]:
        code_blocks = []
        in_code = False
        current_block = []
        
        for p in paragraphs:
            if '```' in p or p.strip().startswith('    '):
                if not in_code:
                    in_code = True
                    current_block = []
                current_block.append(p)
            elif in_code:
                code_blocks.append('\n'.join(current_block))
                in_code = False
                current_block = []
        
        return code_blocks


class DocProcessor(DocumentProcessor):
    """Legacy Word document processor (.doc) - requires antiword or catdoc"""
    
    def __init__(self):
        self.supported_extensions = ['.doc']
    
    def process(self, file_path: Path) -> Optional[Dict]:
        try:
            
            result = subprocess.run(
                ['antiword', str(file_path)],
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore',
                timeout=TIMEOUT_DOCUMENT_CONVERT,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
            )
            
            if result.returncode == 0:
                content = result.stdout
            else:
                result = subprocess.run(
                    ['catdoc', '-w', str(file_path)],
                    capture_output=True,
                    text=True,
                    encoding='utf-8',
                    errors='ignore',
                    timeout=TIMEOUT_DOCUMENT_CONVERT,
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
                )
                if result.returncode != 0:
                    return None
                content = result.stdout
            
            lines = content.split('\n')
            title = lines[0].strip()[:100] if lines else file_path.stem
            
            return {
                'title': title,
                'content': content,
                'content_type': 'doc',
                'size': len(content),
                'line_count': len(lines),
                'hash': hashlib.md5(content.encode()).hexdigest(),
                'sections': [],
                'code_examples': []
            }
        except Exception:
            return None


class PDFProcessor(DocumentProcessor):
    """PDF document processor (.pdf) - requires pdfplumber or PyMuPDF"""
    
    def __init__(self):
        self.supported_extensions = ['.pdf']
        self.has_pdfplumber = self._check_pdfplumber()
        self.has_pymupdf = self._check_pymupdf()
    
    def _check_pdfplumber(self) -> bool:
        try:
            import pdfplumber
            return True
        except ImportError:
            return False
    
    def _check_pymupdf(self) -> bool:
        try:
            import fitz
            return True
        except ImportError:
            return False
    
    def process(self, file_path: Path) -> Optional[Dict]:
        # Prefer PyMuPDF (better performance)
        if self.has_pymupdf:
            return self._process_with_pymupdf(file_path)
        
        # Fallback: use pdfplumber
        if self.has_pdfplumber:
            return self._process_with_pdfplumber(file_path)
        
        # If neither is installed, return a hint message
        return {
            'title': file_path.stem,
            'content': f"PDF processing requires installing dependencies (PyMuPDF is recommended first):\n"
                      f"  pip install PyMuPDF\n"
                      f"  or (fallback)\n"
                      f"  pip install pdfplumber",
            'content_type': 'pdf',
            'size': 0,
            'line_count': 0,
            'hash': '',
            'sections': [],
            'code_examples': [],
            'requires_dependencies': True,
            'install_hint': 'pip install PyMuPDF'
        }
    
    def _process_with_pymupdf(self, file_path: Path) -> Optional[Dict]:
        """Process using PyMuPDF (high performance)"""
        try:
            import fitz
            
            doc = fitz.open(str(file_path))
            
            text_content = []
            sections = []
            
            for page_num, page in enumerate(doc):
                text = page.get_text()
                text_content.append(text)
                
                # Extract titles (based on font size)
                blocks = page.get_text("dict")["blocks"]
                for block in blocks:
                    if "lines" in block:
                        for line in block["lines"]:
                            for span in line["spans"]:
                                if span["size"] > 14:
                                    title = span["text"].strip()
                                    if title and len(title) < 100:
                                        sections.append({'level': 1, 'title': title})
            
            full_text = '\n'.join(text_content)
            metadata = doc.metadata
            title = metadata.get('title') or file_path.stem
            
            doc.close()
            
            return {
                'title': title,
                'content': full_text,
                'content_type': 'pdf',
                'size': len(full_text),
                'line_count': full_text.count('\n') + 1,
                'hash': hashlib.md5(full_text.encode()).hexdigest(),
                'sections': sections[:50],
                'code_examples': [],
                'metadata': {
                    'author': metadata.get('author'),
                    'subject': metadata.get('subject'),
                    'page_count': len(text_content)
                }
            }
        except Exception:
            return None
    
    def _process_with_pdfplumber(self, file_path: Path) -> Optional[Dict]:
        """Process using pdfplumber"""
        try:
            import pdfplumber
            
            text_content = []
            
            with pdfplumber.open(str(file_path)) as pdf:
                metadata = pdf.metadata or {}
                title = metadata.get('Title') or file_path.stem
                
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        text_content.append(text)
                
                full_text = '\n'.join(text_content)
                
                return {
                    'title': title,
                    'content': full_text,
                    'content_type': 'pdf',
                    'size': len(full_text),
                    'line_count': full_text.count('\n') + 1,
                    'hash': hashlib.md5(full_text.encode()).hexdigest(),
                    'sections': [],
                    'code_examples': [],
                    'metadata': {
                        'author': metadata.get('Author'),
                        'page_count': len(pdf.pages)
                    }
                }
        except Exception:
            return None


class EPUBProcessor(DocumentProcessor):
    """EPUB ebook processor - parses directly with zipfile + BeautifulSoup"""
    
    def __init__(self):
        self.supported_extensions = ['.epub']
    
    def process(self, file_path: Path) -> Optional[Dict]:
        try:
            import zipfile
            from xml.etree import ElementTree as ET
            
            with zipfile.ZipFile(str(file_path), 'r') as zf:
                container_xml = zf.read('META-INF/container.xml')
                container_root = ET.fromstring(container_xml)
                
                rootfile_elem = container_root.find('.//{urn:oasis:names:tc:opendocument:xmlns:container}rootfile')
                if rootfile_elem is None:
                    return None
                
                opf_path = rootfile_elem.get('full-path')
                if not opf_path:
                    return None
                
                opf_content = zf.read(opf_path)
                opf_root = ET.fromstring(opf_content)
                
                ns = {'opf': 'http://www.idpf.org/2007/opf'}
                
                manifest = {}
                for item in opf_root.findall('.//opf:item', ns):
                    item_id = item.get('id')
                    href = item.get('href')
                    if item_id and href:
                        manifest[item_id] = href
                
                spine_ids = []
                for itemref in opf_root.findall('.//opf:itemref', ns):
                    idref = itemref.get('idref')
                    if idref in manifest:
                        spine_ids.append(idref)
                
                opf_dir = opf_path.rsplit('/', 1)[0] if '/' in opf_path else ''
                
                text_content = []
                sections = []
                
                for item_id in spine_ids[:100]:
                    href = manifest[item_id]
                    if opf_dir:
                        file_path_in_zip = f"{opf_dir}/{href}"
                    else:
                        file_path_in_zip = href
                    
                    try:
                        html_content = zf.read(file_path_in_zip)
                        
                        if BeautifulSoup:
                            soup = BeautifulSoup(html_content, 'lxml')
                            
                            for heading in soup.find_all(['h1', 'h2', 'h3']):
                                title = heading.get_text().strip()
                                if title and len(title) < 100:
                                    level = int(heading.name[1])
                                    sections.append({'level': level, 'title': title})
                            
                            for script in soup.find_all('script'):
                                script.decompose()
                            for style in soup.find_all('style'):
                                style.decompose()
                            
                            text = soup.get_text(separator='\n', strip=True)
                            if text:
                                text_content.append(text)
                        else:
                            text = html_content.decode('utf-8', errors='ignore')
                            text_content.append(text)
                    except KeyError:
                        continue
                
                full_text = '\n\n'.join(text_content)
                
                title = file_path.stem
                for elem in opf_root.findall('.//opf:title', ns):
                    if elem.text:
                        title = elem.text
                        break
                
                metadata = {}
                for elem in opf_root.findall('.//opf:creator', ns):
                    if elem.text:
                        metadata['author'] = elem.text
                        break
                
                return {
                    'title': title,
                    'content': full_text,
                    'content_type': 'epub',
                    'size': len(full_text),
                    'line_count': full_text.count('\n') + 1,
                    'hash': hashlib.md5(full_text.encode()).hexdigest(),
                    'sections': sections[:50],
                    'code_examples': [],
                    'metadata': metadata
                }
        except Exception:
            return None


class ChmProcessor(DocumentProcessor):
    """Microsoft Compiled HTML Help processor (.chm).

    Uses 7-Zip to extract CHM files, then imports the internal HTML files as documents.
    Requires 7-Zip to be installed on the system (https://www.7-zip.org/).
    """

    # Auxiliary file types skipped during 7z extraction
    EXCLUDE_PATTERNS = [
        '-x!*.png', '-x!*.gif', '-x!*.jpg', '-x!*.jpeg',
        '-x!*.css', '-x!*.js', '-x!*.ico', '-x!*.svg',
        '-x!*.woff', '-x!*.woff2', '-x!*.ttf', '-x!*.eot',
        '-x!*.bmp', '-x!*.webp', '-x!*.avif',
    ]

    def __init__(self):
        self.supported_extensions = ['.chm']
        self._sevenzip_path = None

    def _find_7zip(self) -> Optional[str]:
        if self._sevenzip_path:
            return self._sevenzip_path
        # _find_7zip_path is a static method of GenericDocumentScanner (same module, already loaded at runtime)
        import sys
        _mod = sys.modules[__name__]
        self._sevenzip_path = _mod.GenericDocumentScanner._find_7zip_path()
        return self._sevenzip_path

    def process(self, file_path: Path) -> Optional[List[Dict]]:
        sevenzip = self._find_7zip()
        if not sevenzip:
            return [{
                'title': file_path.stem,
                'content': (
                    '7-Zip must be installed to process CHM files\n\n'
                    'Download address:\n'
                    '  Official site: https://www.7-zip.org/download.html\n'
                    '  SourceForge: https://sourceforge.net/projects/sevenzip/files/7-Zip/\n\n'
                    'Windows 64-bit users can download and install 7z2301-x64.exe'
                ),
                'content_type': 'chm',
                'size': 0, 'line_count': 0, 'hash': '', 'sections': [], 'code_examples': [],
                'requires_dependencies': True,
                'install_hint': 'Requires installing 7-Zip: https://www.7-zip.org/download.html'
            }]

        tmpdir = None
        try:
            # Extract to a temporary directory with 7z (skip auxiliary files such as images/CSS/JS, keep only HTML)
            tmpdir = tempfile.mkdtemp(prefix='chm_')
            result = subprocess.run(
                [sevenzip, 'x', '-y', f'-o{tmpdir}', str(file_path), *self.EXCLUDE_PATTERNS],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=TIMEOUT_DOCUMENT_ARCHIVE_EXTRACT,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
            )
            if result.returncode != 0:
                return None

            # Collect all htm/html files
            extracted_dir = Path(tmpdir)
            html_files = list(extracted_dir.rglob('*.htm')) + list(extracted_dir.rglob('*.html'))
            if not html_files:
                return None

            # Process them one by one with HTMLProcessor
            html_proc = HTMLProcessor()
            docs = []
            seen_hashes = set()
            for hf in html_files:
                try:
                    doc = html_proc.process(hf)
                    if doc:
                        rel_path = str(hf.relative_to(extracted_dir)).replace('\\', '/')
                        doc['path'] = rel_path
                        doc['full_path'] = str(hf)
                        doc['extension'] = '.html'
                        doc['file_size'] = hf.stat().st_size
                        doc['last_modified'] = datetime.fromtimestamp(
                            hf.stat().st_mtime
                        ).isoformat()
                        # Deduplicate
                        doc_hash = doc.get('hash', '')
                        if doc_hash and doc_hash in seen_hashes:
                            continue
                        if doc_hash:
                            seen_hashes.add(doc_hash)
                        docs.append(doc)
                except Exception:
                    continue

            return docs if docs else None

        except Exception:
            return None
        finally:
            if tmpdir:
                shutil.rmtree(tmpdir, ignore_errors=True)
class HlpProcessor(DocumentProcessor):
    """Windows Help file processor (.hlp) — pure Python, outputs Markdown.
    Parses |TTLBTREE to get titles; after decompressing |TOPIC, decodes body through Hall/Phrase.
    Supports HC30/HC31/HCW 4.00 formats, LZ77 compression.
    """

    def __init__(self):
        self.supported_extensions = ['.hlp']

    # ═══════════════════════════════════════════
    #  Public entry point — split into multiple documents by RT2 topic header
    # ═══════════════════════════════════════════

    def process(self, file_path: Path) -> Optional[List[Dict]]:
        try:
            with open(file_path, 'rb') as f:
                header = f.read(16)
                if len(header) < 16:
                    return None
                magic, dir_start, _fb, _fs = struct.unpack('<LLLl', header)
                if magic != 0x00035F3F:
                    return None

                internal_files = self._parse_directory(f, dir_start)
                if not internal_files or '|SYSTEM' not in internal_files:
                    return None

                system_info = self._read_system(f, internal_files)
                if not system_info:
                    return None

                phrases = self._parse_phrases(f, internal_files, system_info)
                titles = self._read_ttlbtree(f, internal_files)
                topic_list = self._extract_topic_text(f, internal_files, system_info, phrases, titles)

        except Exception:
            return None

        if not topic_list:
            return None

        docs = []
        for title, body_text in topic_list:
            if not title and not body_text:
                continue
            content_parts = [f'## {title}'] if title else []
            if body_text:
                content_parts.append(body_text)
            content = '\n\n'.join(content_parts)
            content = re.sub(r'\n{3,}', '\n\n', content).strip()
            if not content:
                continue

            sections = [{'level': 2, 'title': title}] if title else []
            code_examples = re.findall(r'```[\w]*\n(.*?)```', content, re.DOTALL)

            docs.append({
                'title': (title or file_path.stem)[:200],
                'content': content,
                'content_type': 'hlp',
                'size': len(content),
                'line_count': content.count('\n') + 1,
                'hash': hashlib.md5(content.encode()).hexdigest(),
                'sections': sections,
                'code_examples': code_examples
            })

        return docs if docs else None

    # ═══════════════════════════════════════════
    #  Directory B+ tree
    # ═══════════════════════════════════════════

    def _parse_directory(self, f, dir_start):
        f.seek(dir_start + 9)
        f.read(2); f.read(2)
        page_size = struct.unpack('<H', f.read(2))[0]
        f.read(16); f.read(2); f.read(2)
        root_page = struct.unpack('<h', f.read(2))[0]
        f.read(2); f.read(2)
        nlevels = struct.unpack('<h', f.read(2))[0]
        f.read(4)

        def read_leaf_fn(fh, n):
            r = []
            for _ in range(n):
                nb = bytearray()
                while True:
                    b = fh.read(1)
                    if b in (b'\x00', b''): break
                    nb.extend(b)
                r.append((nb.decode('latin-1', errors='replace'),
                          struct.unpack('<L', fh.read(4))[0]))
            return r

        page_start = dir_start + 9 + 38
        entries = self._traverse_btree_leaves(f, page_start, root_page, nlevels, page_size, read_leaf_fn)
        return dict(entries)

    def _traverse_btree_leaves(self, f, page_start, root_page, nlevels, page_size, read_leaf_fn):
        page_num = root_page
        for _ in range(nlevels - 1):
            f.seek(page_start + page_num * page_size)
            f.read(2); nentries = struct.unpack('<h', f.read(2))[0]
            prev_page = struct.unpack('<h', f.read(2))[0]
            names = []
            for __ in range(nentries):
                nb = bytearray()
                while True:
                    b = f.read(1)
                    if b in (b'\x00', b''): break
                    nb.extend(b)
                names.append(struct.unpack('<h', f.read(2))[0])
            page_num = prev_page if prev_page != -1 else (names[0] if names else -1)

        results = []
        while page_num not in (-1, 0xFFFF):
            f.seek(page_start + page_num * page_size)
            f.read(2); nentries = struct.unpack('<h', f.read(2))[0]
            f.read(2); next_page = struct.unpack('<h', f.read(2))[0]
            results.extend(read_leaf_fn(f, nentries))
            page_num = next_page
        return results

    # ═══════════════════════════════════════════
    #  |SYSTEM
    # ═══════════════════════════════════════════

    def _read_system(self, f, internal_files):
        sys_offset = internal_files.get('|SYSTEM')
        if sys_offset is None:
            return None
        f.seek(sys_offset); f.read(4); f.read(4); f.read(1)
        data_start = sys_offset + 9
        f.seek(data_start)
        magic = struct.unpack('<H', f.read(2))[0]
        if magic != 0x036C: return None
        minor = struct.unpack('<h', f.read(2))[0]
        f.read(2); f.read(4)
        flags = struct.unpack('<H', f.read(2))[0]

        tb_size = 4096 if (minor > 16 and (flags & 4)) else 2048
        compressed = minor > 16 and (flags & 0xC)
        has_hall = ('|PhrIndex' in internal_files) and ('|PhrImage' in internal_files)
        has_old_phrases = '|Phrases' in internal_files
        return {'topic_block_size': tb_size, 'compressed': compressed,
                'minor': minor, 'has_hall': has_hall, 'has_old_phrases': has_old_phrases}

    # ═══════════════════════════════════════════
    #  Phrase table (Hall / old-style)
    # ═══════════════════════════════════════════

    def _parse_phrases(self, f, internal_files, system_info):
        if system_info.get('has_hall'):
            return self._parse_phrases_hall(f, internal_files)
        if system_info.get('has_old_phrases'):
            return self._parse_phrases_old(f, internal_files)
        return None

    # ── Hall (|PhrIndex + |PhrImage) ──

    def _parse_phrases_hall(self, f, internal_files):
        idx_off = internal_files.get('|PhrIndex')
        img_off = internal_files.get('|PhrImage')
        if not idx_off or not img_off:
            return None

        f.seek(idx_off); f.read(4); idx_used = struct.unpack('<L', f.read(4))[0]; f.read(1)
        idx_start = idx_off + 9
        f.seek(idx_start)
        idx_data = f.read(idx_used)

        magic = struct.unpack_from('<L', idx_data, 0)[0]
        if magic != 1: return None
        nentries = struct.unpack_from('<L', idx_data, 4)[0]
        img_size = struct.unpack_from('<L', idx_data, 12)[0]
        img_comp_size = struct.unpack_from('<L', idx_data, 16)[0]
        flags = struct.unpack_from('<H', idx_data, 24)[0]
        bit_count = flags & 0xF

        offsets = self._build_phrase_offsets(idx_data, 28, nentries, bit_count)
        if not offsets or len(offsets) < nentries + 1:
            return None

        f.seek(img_off); f.read(4); img_used = struct.unpack('<L', f.read(4))[0]; f.read(1)
        img_start = img_off + 9
        f.seek(img_start)
        img_raw = f.read(img_used)

        if img_comp_size != img_size:
            img_data = self._lz77_decompress(img_raw, img_size)
        else:
            img_data = img_raw

        phrases = []
        for i in range(nentries):
            s, e = offsets[i], offsets[i + 1]
            if s < len(img_data) and e <= len(img_data):
                phrases.append(img_data[s:e].decode('latin-1', errors='replace'))
            else:
                phrases.append('')
        return phrases

    def _build_phrase_offsets(self, data, start_offset, nentries, bit_count):
        byte_data = bytearray(data)
        ptr_idx = start_offset
        mask = 0
        value = 0

        def get_bit():
            nonlocal ptr_idx, mask, value
            mask = (mask << 1) & 0xFFFFFFFF  # Python ints don't overflow
            if mask == 0:
                if ptr_idx + 4 <= len(byte_data):
                    value = struct.unpack_from('<L', byte_data, ptr_idx)[0]
                else:
                    value = 0
                ptr_idx += 4
                mask = 1
            return (value & mask) != 0

        offsets = [0]
        for _ in range(nentries):
            n = 1
            while get_bit():
                n += 1 << bit_count
            if get_bit(): n += 1
            if bit_count > 1 and get_bit(): n += 2
            if bit_count > 2 and get_bit(): n += 4
            if bit_count > 3 and get_bit(): n += 8
            if bit_count > 4 and get_bit(): n += 16
            offsets.append(offsets[-1] + n)
        return offsets

    # ── old-style (|Phrases) ──

    def _parse_phrases_old(self, f, internal_files):
        phr_offset = internal_files.get('|Phrases')
        if phr_offset is None: return None
        f.seek(phr_offset); f.read(4); phr_used = struct.unpack('<L', f.read(4))[0]; f.read(1)
        phr_start = phr_offset + 9
        f.seek(phr_start)
        data = f.read(phr_used)
        if len(data) < 4: return None

        num_phrases = struct.unpack_from('<H', data, 0)[0]
        one_hundred = struct.unpack_from('<H', data, 2)[0]
        offsets = []
        pos = 4
        for _ in range(num_phrases + 1):
            offsets.append(struct.unpack_from('<H', data, pos)[0])
            pos += 2

        hdr_end = 4 + (num_phrases + 1) * 2
        if one_hundred == 0x0100 and len(data) > hdr_end + 4:
            decomp_size = struct.unpack_from('<L', data, hdr_end)[0]
            lz77_data = data[hdr_end + 4:]
            phrase_bytes = self._lz77_decompress(lz77_data, max(decomp_size, 65536))
            if not phrase_bytes:
                return None
        else:
            phrase_bytes = data[hdr_end:]

        phrases = []
        for i in range(num_phrases):
            s, e = offsets[i], offsets[i + 1]
            if s < len(phrase_bytes) and e <= len(phrase_bytes):
                phrases.append(phrase_bytes[s:e].decode('latin-1', errors='replace'))
            else:
                phrases.append('')
        return phrases

    # ═══════════════════════════════════════════
    #  |TOPIC text extraction (including Hall / Phrase decompression)
    # ═══════════════════════════════════════════

    def _extract_topic_text(self, f, internal_files, system_info, phrases, titles):
        """Walk TOPICLINKs, group text by RT2 topic headers. Returns [(title, text)]."""
        topic_offset = internal_files.get('|TOPIC')
        if topic_offset is None:
            return []

        f.seek(topic_offset); f.read(4)
        topic_used = struct.unpack('<L', f.read(4))[0]; f.read(1)
        data_start = topic_offset + 9

        tb_size = system_info['topic_block_size']
        compressed = system_info['compressed']
        has_phrases = phrases is not None
        use_hall = system_info.get('has_hall', False)

        all_data = bytearray()
        offset = data_start
        while offset < data_start + topic_used:
            f.seek(offset); f.read(12)
            raw = f.read(tb_size - 12)
            if compressed:
                all_data.extend(self._lz77_decompress(raw, 16384))
            else:
                all_data.extend(raw)
            offset += tb_size

        topics = []  # [(title, [text_runs])]
        current_title = 'Unknown'
        current_texts = []

        title_index = 0
        pos = 0
        while pos + 21 <= len(all_data):
            bsz = struct.unpack_from('<L', all_data, pos)[0]
            if 10 <= bsz <= 4000:
                rt = all_data[pos + 20]
                dl2 = struct.unpack_from('<L', all_data, pos + 4)[0]
                dl1 = struct.unpack_from('<L', all_data, pos + 16)[0]

                if 21 < dl1 < bsz:
                    compressed_sz = bsz - dl1
                    ld2_raw = all_data[pos + dl1: pos + bsz]

                    ld2 = b''
                    if compressed_sz > 0 and dl2 > 0:
                        if has_phrases:
                            if dl2 <= compressed_sz:
                                ld2 = ld2_raw[:dl2]
                            elif use_hall:
                                ld2 = self._hall_decompress_bytes(ld2_raw, phrases, dl2)
                            else:
                                ld2 = self._phrase_decompress_bytes(ld2_raw, phrases, dl2)
                        else:
                            ld2 = ld2_raw

                    if rt == 2:
                        # Save previous topic
                        if title_index > 0:
                            topics.append((current_title, current_texts))
                            current_texts = []

                        # Extract title from LinkData2 first NUL-term string
                        title = self._extract_topic_header_text(ld2) if ld2 else ''
                        # Fallback to TTLBTREE title
                        if not title and title_index < len(titles):
                            title = titles[title_index][1]
                        current_title = title or f'Topic {title_index}'
                        title_index += 1

                    elif rt in (0x20, 0x23, 0x27) and ld2:
                        ld1 = all_data[pos + 21: pos + dl1]
                        t = self._extract_display_text(ld1, ld2)
                        if t:
                            words = t.split()
                            ratio = sum(1 for w in words if len(w) > 2) / max(len(words), 1)
                            if ratio > 0.3 or len(t) > 40:
                                current_texts.append(t)

                    pos += bsz
                    continue
            pos += 1

        # Last topic
        if title_index > 1 or (not topics and current_texts):
            topics.append((current_title, current_texts))

        # Merge text runs per topic
        result = []
        for i, (t_title, texts) in enumerate(topics):
            # Use TTLBTREE title when available (cleaner)
            if i < len(titles):
                t_title = titles[i][1]
            merged = '\n\n'.join(texts)
            merged = re.sub(r'\n{3,}', '\n\n', merged)
            result.append((t_title, merged))

        return result

    # ── RT=2 topic header: LinkData2 = NUL-separated title + macros ──

    @staticmethod
    def _extract_topic_header_text(ld2):
        """LinkData2 for RecordType 2: first NUL-terminated string is topic title."""
        parts = ld2.split(b'\x00')
        texts = []
        for part in parts:
            s = part.decode('latin-1', errors='replace')
            s = HlpProcessor._clean_text(s)
            if s:
                texts.append(s)
        return ' '.join(texts)

    # ── RT=0x20 display paragraph: LinkData1 has format header, LinkData2 = NUL-separated text ──

    @staticmethod
    def _extract_display_text(ld1, ld2):
        """Extract text from a display paragraph (RecordType 0x20/0x23/0x27).
        LinkData1 starts with format info; LinkData2 is NUL-terminated strings
        alternating with format control bytes from LinkData1."""
        off = 0

        # Skip expanded size (compressed long)
        off = HlpProcessor._skip_compressed_long(ld1, off)
        # Skip topic offset increment (word)
        off += 2

        # Parse ParagraphInfo flags (word)
        if off + 2 > len(ld1):
            return ''
        x2 = struct.unpack_from('<H', ld1, off)[0]
        off += 2

        # Skip conditional fields based on flags
        if x2 & 0x0001: off = HlpProcessor._skip_compressed_long(ld1, off)
        if x2 & 0x0002: off = HlpProcessor._skip_int(ld1, off)
        if x2 & 0x0004: off = HlpProcessor._skip_int(ld1, off)
        if x2 & 0x0008: off = HlpProcessor._skip_int(ld1, off)
        if x2 & 0x0010: off = HlpProcessor._skip_int(ld1, off)
        if x2 & 0x0020: off = HlpProcessor._skip_int(ld1, off)
        if x2 & 0x0040: off = HlpProcessor._skip_int(ld1, off)
        if x2 & 0x0100: off += 4  # border info (byte + word)
        if x2 & 0x0200:
            if off >= len(ld1): return ''
            ntabs = HlpProcessor._scan_int(ld1, off)
            off = HlpProcessor._skip_int(ld1, off)
            for _ in range(ntabs):
                if off + 2 > len(ld1): break
                tab = struct.unpack_from('<H', ld1, off)[0]
                off += 2
                if tab & 0x4000:
                    off += 2

        # Now iterate: read NUL-term string from ld2, then format byte from ld1.
        # Build paragraphs: LF(0x81)/CR(0x82)→soft break, 0xFF→paragraph end.
        paragraphs = []
        current = []
        ld2_pos = 0
        while ld2_pos < len(ld2):
            end = ld2.find(b'\x00', ld2_pos)
            if end < 0:
                end = len(ld2)
            s = ld2[ld2_pos:end].decode('latin-1', errors='replace')
            s = HlpProcessor._clean_text(s)
            if s:
                current.append(s)
            ld2_pos = end + 1

            if off >= len(ld1):
                break
            ctrl = ld1[off]
            if ctrl == 0xFF:
                if current:
                    paragraphs.append(' '.join(current))
                    current = []
                off += 1
                break  # end of paragraph
            elif ctrl in (0x81, 0x82):           # LF / CR → soft break
                if current:
                    paragraphs.append(' '.join(current))
                    current = []
                off += 1
            elif ctrl == 0x80: off += 3          # font change
            elif ctrl == 0x20: off += 5          # variable field
            elif ctrl == 0x21: off += 3          # dtype
            elif ctrl == 0x83: off += 4
            elif ctrl == 0x84: off += 5
            elif ctrl == 0x85: off += 6
            elif ctrl == 0x86: off += 7
            elif ctrl == 0x87: off += 8
            elif ctrl == 0x88: off += 9
            elif ctrl == 0x89: off += 10
            elif ctrl == 0x8A: off += 11
            elif ctrl == 0x8B: off += 12
            elif ctrl == 0x8C: off += 13
            elif ctrl == 0x23: off += 1          # topic separator
            else: off += 1

        if current:
            paragraphs.append(' '.join(current))
        return '\n\n'.join(paragraphs)

    # ── Compressed number helpers ──

    @staticmethod
    def _skip_compressed_long(data, off):
        while off < len(data) and (data[off] & 0x80):
            off += 1
        return off + 1

    @staticmethod
    def _skip_int(data, off):
        b = data[off]
        if b & 0x80:
            return off + 2
        return off + 1

    @staticmethod
    def _scan_int(data, off):
        b = data[off]
        if b & 0x80:
            return (b & 0x7F) | (data[off + 1] << 7)
        return b

    # ── Hall LinkData2 decompression ──

    @staticmethod
    def _hall_decompress(data, phrases, expected_len):
        return HlpProcessor._hall_decompress_bytes(data, phrases, expected_len).decode('latin-1', errors='replace')

    @staticmethod
    def _hall_decompress_bytes(data, phrases, expected_len):
        """Hall decompression, returns raw bytes (NUL-separated text fragments)."""
        result = bytearray()
        i = 0
        data_bytes = bytearray(data)
        while i < len(data_bytes):
            ch = data_bytes[i]
            if ch & 15 == 15:  i += 1
            elif ch & 15 == 7: result.append(0x20); i += 1
            elif ch & 7 == 3:
                copy_len = (ch >> 3) + 1; i += 1
                end = min(i + copy_len, len(data_bytes))
                result.extend(data_bytes[i:end])
                i = end
            elif ch & 3 == 1:
                if i + 1 >= len(data_bytes): break
                phrase_num = ch * 64 + 64 + data_bytes[i + 1]; i += 2
                if 0 <= phrase_num < len(phrases):
                    result.extend(phrases[phrase_num].encode('latin-1', errors='replace'))
            elif ch % 2 == 0:
                phrase_num = ch // 2; i += 1
                if 0 <= phrase_num < len(phrases):
                    result.extend(phrases[phrase_num].encode('latin-1', errors='replace'))
            else: i += 1
        return bytes(result[:expected_len])

    # ── old-style Phrase LinkData2 decompression ──

    @staticmethod
    def _phrase_decompress(data, phrases, expected_len):
        return HlpProcessor._phrase_decompress_bytes(data, phrases, expected_len).decode('latin-1', errors='replace')

    @staticmethod
    def _phrase_decompress_bytes(data, phrases, expected_len):
        result = bytearray()
        i = 0
        data_bytes = bytearray(data)
        while i < len(data_bytes):
            ch = data_bytes[i]
            if ch == 0 or ch >= 16:
                result.append(ch)
                i += 1
            else:
                if i + 1 >= len(data_bytes): break
                val = ch * 256 - 256 + data_bytes[i + 1]; i += 2
                phrase_num = val // 2
                if 0 <= phrase_num < len(phrases):
                    result.extend(phrases[phrase_num].encode('latin-1', errors='replace'))
                    if val % 2 == 1: result.append(0x20)
        return bytes(result[:expected_len])

    # ── Shared post-processing ──

    @staticmethod
    def _clean_text(raw):
        """Strip non-printable chars, collapse whitespace."""
        clean = []
        for c in raw:
            if 32 <= ord(c) < 127: clean.append(c)
            elif c in '\n\r\t': clean.append(' ')
        return re.sub(r'\s+', ' ', ''.join(clean)).strip()

    # ═══════════════════════════════════════════
    #  LZ77 decompression (ring buffer, zero-init)
    # ═══════════════════════════════════════════

    @staticmethod
    def _lz77_decompress(data, max_output=16384):
        output = bytearray()
        ring = bytearray(b'\x00' * 4096)
        ring_pos = 0
        src = bytearray(data)
        src_idx = bit_buf = bits_left = 0

        while len(output) < max_output and src_idx < len(src):
            if bits_left == 0:
                if src_idx >= len(src): break
                bit_buf, src_idx, bits_left = src[src_idx], src_idx + 1, 8
            if bit_buf & 1:
                if src_idx + 1 >= len(src): break
                low, high = src[src_idx], src[src_idx + 1]; src_idx += 2
                pos_rel = low | ((high & 0xF) << 8)
                length = (high >> 4) + 3
                for _ in range(length):
                    if len(output) >= max_output: break
                    b = ring[(ring_pos - 1 - pos_rel) & 0xFFF]
                    output.append(b)
                    ring[ring_pos & 0xFFF] = b
                    ring_pos = (ring_pos + 1) & 0xFFF
                # DON'T reset bits_left — continue processing remaining bits
                # from current bit_buf (same as helpdeco: mask shifts until overflow)
            else:
                if src_idx >= len(src): break
                b = src[src_idx]; src_idx += 1
                output.append(b)
                ring[ring_pos & 0xFFF] = b
                ring_pos = (ring_pos + 1) & 0xFFF
            bit_buf >>= 1; bits_left -= 1
        return bytes(output)

    # ═══════════════════════════════════════════
    #  |TTLBTREE → titles
    # ═══════════════════════════════════════════

    def _read_ttlbtree(self, f, internal_files):
        ttl_offset = internal_files.get('|TTLBTREE')
        if ttl_offset is None: return []
        f.seek(ttl_offset); f.read(4); f.read(4); f.read(1)
        ttl_start = ttl_offset + 9
        f.seek(ttl_start); f.read(2); f.read(2)
        ttl_psize = struct.unpack('<H', f.read(2))[0]
        f.read(16); f.read(2); f.read(2)
        ttl_root = struct.unpack('<h', f.read(2))[0]
        f.read(2); f.read(2)
        ttl_nlevels = struct.unpack('<h', f.read(2))[0]; f.read(4)

        def read_ttl_leaf(fh, n):
            r = []
            for _ in range(n):
                off = struct.unpack('<L', fh.read(4))[0]
                nb = bytearray()
                while True:
                    b = fh.read(1)
                    if b in (b'\x00', b''): break
                    nb.extend(b)
                r.append((off, nb.decode('latin-1', errors='replace')))
            return r

        ttl_pstart = ttl_start + 38
        return self._traverse_btree_leaves(f, ttl_pstart, ttl_root, ttl_nlevels, ttl_psize, read_ttl_leaf)
class WebDocumentProcessor:
    """Web document processor (online documents) — uses html2text for conversion, no BeautifulSoup required"""
    
    def __init__(self):
        if not html2text:
            raise ImportError("html2text is required: pip install html2text")
        
        self.converter = html2text.HTML2Text()
        self.converter.ignore_links = False
        self.converter.ignore_images = True
        self.converter.body_width = 0
    
    def process_url(self, url: str, timeout: int = 30) -> Optional[Dict]:
        try:
            import requests
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(url, headers=headers, timeout=timeout)
            response.encoding = response.apparent_encoding or 'utf-8'
            
            html_content = response.text
            
            # Extract <title> with regex (first match is sufficient)
            title_match = re.search(r'<title[^>]*>(.*?)</title>', html_content, re.IGNORECASE | re.DOTALL)
            title = title_match.group(1).strip() if title_match else url
            
            # html2text converts HTML to Markdown
            markdown = self.converter.handle(html_content)
            
            return {
                'title': title,
                'content': markdown,
                'content_type': 'web',
                'url': url,
                'size': len(markdown),
                'line_count': markdown.count('\n') + 1,
                'hash': hashlib.md5(markdown.encode()).hexdigest(),
                'sections': [],
                'code_examples': []
            }
        except Exception:
            return None


def _has_lxml() -> bool:
    try:
        import lxml
        return True
    except ImportError:
        return False


def _pool_worker(work_queue, result_queue, directory_str):
    """
    Pool worker: takes file paths from work_queue, processes them, and puts results into result_queue.
    Exits after receiving a None sentinel, and sends None back through result_queue to notify the consumer.
    """
    directory = Path(directory_str)
    processors = [
        TextProcessor(),
        MarkdownProcessor(),
        HTMLProcessor(),
        DocxProcessor(),
        DocProcessor(),
        PDFProcessor(),
        EPUBProcessor(),
        ChmProcessor(),
        HlpProcessor()
    ]

    for file_path_str in iter(work_queue.get, None):
        file_path = Path(file_path_str)
        try:
            stat_info = file_path.stat()
            for processor in processors:
                if processor.can_process(file_path):
                    results = processor.process(file_path)
                    if results:
                        rel_path = str(file_path.relative_to(directory)).replace('\\', '/')
                        common_meta = {
                            'full_path': str(file_path),
                            'extension': file_path.suffix.lower(),
                            'file_size': stat_info.st_size,
                            'last_modified': datetime.fromtimestamp(stat_info.st_mtime).isoformat()
                        }

                        if isinstance(results, list):
                            for item in results:
                                item.setdefault('path', rel_path)
                                item.update(common_meta)
                                if not item.get('path') or item['path'] == rel_path:
                                    item['path'] = f"{rel_path}#{item.get('title', 'untitled')}"
                                result_queue.put(item)
                        else:
                            results['path'] = rel_path
                            results.update(common_meta)
                            result_queue.put(results)
                    break
        except Exception:
            pass

    result_queue.put(None)  # Sentinel: this worker has finished


class GenericDocumentScanner:
    """Generic document scanner"""
    
    SUPPORTED_EXTENSIONS = [
        '.txt', '.md', '.markdown',
        '.htm', '.html',
        '.docx', '.doc',
        '.pdf', '.epub',
        '.hlp', '.chm'
    ]
    
    def __init__(self, kb_dir: str, config: Optional[Dict] = None, progress_callback: Optional[Callable] = None):
        self.kb_dir = Path(kb_dir)
        self.config = config or self._load_config()
        self.progress_callback = progress_callback
        
        # ZVec collections are stored directly in the kb_dir root
        self.zvec_dir = self.kb_dir
        
        self._scanning = False
        self._scan_thread: Optional[threading.Thread] = None
    
    @staticmethod
    def _detect_language(title: str, content: str = '') -> str:
        """
        Detect document language
        
        Args:
            title: Document title
            content: Document content
        
        Returns:
            Language code: 'zh' (Chinese), 'ja' (Japanese), 'ko' (Korean), 'en' (English), 'other' (Other)
        """
        import re
        
        # Merge title and first 1000 characters of content for detection
        sample = (title + ' ' + content[:1000])
        
        # Count characters for each language
        zh_chars = len(re.findall(r'[\u4e00-\u9fff]', sample))
        ja_chars = len(re.findall(r'[\u3040-\u309f\u30a0-\u30ff]', sample))
        ko_chars = len(re.findall(r'[\uac00-\ud7af]', sample))
        en_chars = len(re.findall(r'[A-Za-z]', sample))
        
        # Select the language with the most characters
        counts = {'zh': zh_chars, 'ja': ja_chars, 'ko': ko_chars, 'en': en_chars}
        max_lang = max(counts, key=counts.get)
        
        # If the maximum character count is too small, return other
        if counts[max_lang] < 10:
            return 'other'
        
        return max_lang
    
    @staticmethod
    def _find_7zip_path() -> Optional[str]:
        """Find the 7-Zip executable path"""
        tools_dir = Path(__file__).parent.parent.parent.parent / 'tools'
        candidates = [str(tools_dir / '7z' / '7z.exe')]
        for name in ('7z', '7z.exe'):
            found = shutil.which(name)
            if found:
                candidates.append(found)
        for p in candidates:
            if Path(p).exists():
                return p
        return None

    @staticmethod
    def _estimate_total_docs(all_files: List[Path]) -> int:
        """Estimate the total number of documents for scanning (expanding subdocuments inside CHM) for accurate progress"""
        estimated = 0
        sevenzip = GenericDocumentScanner._find_7zip_path()
        for f in all_files:
            suffix = f.suffix.lower()
            if suffix == '.chm' and sevenzip:
                try:
                    result = subprocess.run(
                        [sevenzip, 'l', '-ba', str(f)],
                        capture_output=True, text=True, timeout=TIMEOUT_DOCUMENT_ARCHIVE_LIST,
                        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
                    )
                    if result.returncode == 0:
                        html_count = sum(1 for line in result.stdout.strip().split('\n') if line.strip())
                        estimated += max(html_count, 1)
                    else:
                        estimated += 5000
                except Exception:
                    estimated += 5000
            elif suffix in ('.chm', '.hlp', '.epub'):
                estimated += 5000
            else:
                estimated += 1
        return max(estimated, 1)

    def _load_config(self) -> Dict:
        """Load configuration file"""
        config_path = self.kb_dir / "config.json"
        if config_path.exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.debug("Ignoring non-fatal exception: %s", str(e))
        
        return {
            'database': {'file': 'documents.sqlite'},
            'build': {
                'parallel_workers': None,
                'batch_size': 50,
                'supported_extensions': self.SUPPORTED_EXTENSIONS
            }
        }
    
    def save_config(self):
        """Save configuration to file"""
        config_path = self.kb_dir / "config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        
        default_config = {
            'name': 'document-knowledge-base',
            'type': 'generic-documents',
            'version': '1.0',
            'database': {
                'file': 'documents.sqlite'
            },
            'build': {
                'parallel_workers': None,
                'batch_size': 50,
                'supported_extensions': self.SUPPORTED_EXTENSIONS
            }
        }
        
        merged = {**default_config, **self.config}
        
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(merged, f, indent=2, ensure_ascii=False)

    def _clean_zvec_files(self):
        """Clear ZVec data files under kb_dir"""
        import shutil
        for item in list(self.kb_dir.iterdir()):
            name = item.name
            if name.startswith(("scalar", "fts", "idmap", "del.", "manifest", "LOCK", "LOG", "CURRENT", "IDENTITY", "OPTIONS")):
                if item.is_dir():
                    shutil.rmtree(str(item), ignore_errors=True)
                else:
                    try:
                        item.unlink()
                    except Exception:
                        pass
    
    def scan_directory(self, directory: str, extensions: Optional[List[str]] = None,
                      max_workers: Optional[int] = None,
                      exclude: Optional[List[str]] = None,
                      rebuild: bool = False) -> Dict:
        """
        Scan documents in a directory
        
        Args:
            directory: Directory to scan
            extensions: List of file extensions to process
            max_workers: Maximum number of worker processes
            exclude: List of subdirectory names to exclude (by default excludes multilingual help subdirectories)
            rebuild: Whether to force rebuild (skip mtime comparison and reprocess all files)
        
        Returns:
            Scan statistics
        """
        directory = Path(directory)
        if not directory.exists():
            return {'error': f'Directory does not exist: {directory}'}
        
        extensions = extensions or self.config.get('build', {}).get('supported_extensions', self.SUPPORTED_EXTENSIONS)
        extensions = [e.lower() for e in extensions]
        
        exclude_set = set(exclude) if exclude else DEFAULT_EXCLUDE_DIRS
        
        all_files = []
        for ext in extensions:
            for f in directory.rglob(f'*{ext}'):
                # Exclude language subdirectories (such as ja/, fr/, de/, etc.)
                if exclude_set.intersection(f.relative_to(directory).parts):
                    continue
                all_files.append(f)
        
        if not all_files:
            return {'total_files': 0, 'processed': 0, 'failed': 0}
        
        total_files = len(all_files)
        estimated_total = self._estimate_total_docs(all_files)
        
        parallel_workers_config = self.config.get('build', {}).get('parallel_workers')
        if max_workers is None:
            if parallel_workers_config:
                max_workers = max(1, parallel_workers_config)
            else:
                cpu_cores = cpu_count()
                # At least 2 workers (help knowledge base strategy: max(2, cpu_cores-1)), not exceeding the number of files
                max_workers = min(max(2, cpu_cores - 1), total_files)
        
        batch_size_config = self.config.get('build', {}).get('batch_size', 50)
        # chunksize cannot exceed the average number of files per worker, otherwise heavy files will pile up
        files_per_worker = max(1, total_files // max_workers) if max_workers > 0 else 50
        chunk_size = min(max(1, files_per_worker), max(20, batch_size_config))
        
        processed = 0
        failed = 0
        warnings = []
        install_hints = []
        
        # Check PDF file dependencies
        if '.pdf' in extensions:
            has_pymupdf = False
            has_pdfplumber = False
            try:
                import fitz
                has_pymupdf = True
            except ImportError:
                pass
            try:
                import pdfplumber
                has_pdfplumber = True
            except ImportError:
                pass
            
            pdf_files = [f for f in all_files if f.suffix.lower() == '.pdf']
            if pdf_files and not (has_pymupdf or has_pdfplumber):
                warnings.append(f"Found {len(pdf_files)} PDF files, but dependencies are missing (PyMuPDF or pdfplumber)")
                install_hints.append({
                    'type': 'pdf',
                    'message': 'PDF processing requires installing dependencies (PyMuPDF is recommended first)',
                    'commands': ['pip install PyMuPDF', 'pip install pdfplumber'],
                    'affected_files': len(pdf_files)
                })
        
        # Check DOCX file dependencies
        if '.docx' in extensions:
            has_docx = False
            try:
                from docx import Document
                has_docx = True
            except ImportError:
                pass
            
            docx_files = [f for f in all_files if f.suffix.lower() == '.docx']
            if docx_files and not has_docx:
                warnings.append(f"Found {len(docx_files)} DOCX files, but the dependency is missing (python-docx)")
                install_hints.append({
                    'type': 'docx',
                    'message': 'Word .docx processing requires installing dependencies',
                    'commands': ['pip install python-docx'],
                    'affected_files': len(docx_files)
                })
        
        # Check DOC file dependencies (requires system tools)
        if '.doc' in extensions:
            doc_files = [f for f in all_files if f.suffix.lower() == '.doc']
            if doc_files:
                has_antiword = shutil.which('antiword') is not None
                has_catdoc = shutil.which('catdoc') is not None
                
                if not (has_antiword or has_catdoc):
                    warnings.append(f"Found {len(doc_files)} DOC files, but tools are missing (antiword or catdoc)")
                    install_hints.append({
                        'type': 'doc',
                        'message': 'Word .doc processing requires installing system tools',
                        'commands': ['winget install antiword', 'choco install catdoc', 'or download from the official website'],
                        'affected_files': len(doc_files),
                        'note': 'This is a system-level tool, not a Python package'
                    })
        
        import time; _build_start = time.time()
        
        if rebuild:
            logger.info("Force rebuild: clearing old ZVec data...")
            self._clean_zvec_files()
            # Rebuild mode: process all files
            changed = list(all_files)
            skipped = 0
        else:
            # ZVec does not currently support incremental updates, so reprocess everything (an mtime tracking file can be added later)
            changed = list(all_files)
        
        skipped = total_files - len(changed)
        all_files = changed
        
        if not all_files:
            return {'total_files': total_files, 'processed': 0, 'failed': 0,
                    'skipped': skipped, 'warnings': warnings, 'install_hints': install_hints}
        
        # ZVec requires creation in an empty directory, so use a temporary subdirectory approach
        col_schema = zvec.CollectionSchema("documents", fields=[
            zvec.FieldSchema("chunk_text", zvec.DataType.STRING, index_param=zvec.FtsIndexParam(tokenizer_name="jieba")),
            zvec.FieldSchema("path", zvec.DataType.STRING),
            zvec.FieldSchema("content_type", zvec.DataType.STRING),
            zvec.FieldSchema("extension", zvec.DataType.STRING),
        ])
        import uuid
        tmp_zvec_name = f".zvec_tmp_{uuid.uuid4().hex[:8]}"
        tmp_zvec_path = self.kb_dir / tmp_zvec_name
        col = zvec.create_and_open(str(tmp_zvec_path), schema=col_schema)

        BATCH_SIZE = 500  # Number of inserts per batch
        batch_buffer = []

        try:
            import multiprocessing as mp
            ctx = mp.get_context('spawn')
            # work_queue: file paths distributed to workers (no size limit)
            # result_queue: bounded queue; when it exceeds 200 entries, apply backpressure to workers to prevent memory spikes
            work_queue = ctx.Queue()
            result_queue = ctx.Queue(maxsize=200)

            # Put all file paths into work_queue + one None sentinel for each worker
            for f in all_files:
                work_queue.put(str(f))
            for _ in range(max_workers):
                work_queue.put(None)

            # Start a fixed number of worker processes
            workers = []
            for _ in range(max_workers):
                p = ctx.Process(
                    target=_pool_worker,
                    args=(work_queue, result_queue, str(directory)),
                )
                p.start()
                workers.append(p)

            # Consumer loop: read results from result_queue and write them to ZVec in batches
            workers_remaining = max_workers

            while workers_remaining > 0:
                try:
                    item = result_queue.get(timeout=TIMEOUT_DOCUMENT_WORKER_RESULT)
                except mp.queues.Empty:
                    alive = sum(1 for p in workers if p.is_alive())
                    if alive == 0:
                        break
                    continue

                if item is None:
                    workers_remaining -= 1
                    continue

                result = item
                if result.get('requires_dependencies'):
                    failed += 1
                    continue

                try:
                    title = result.get('title', '')
                    content = result.get('content', '')

                    content = re.sub(
                        r'data:image/[^;]+;base64,[A-Za-z0-9+/=]{100,}',
                        '[Base64 Image]',
                        content
                    )

                    content_lines = content.split('\n')
                    chunk_sz = CHUNK_SIZE_DOCUMENT_LINES
                    chm_name = Path(result.get('full_path', '')).stem
                    html_path = result.get('path') or ''
                    path_val = f"{chm_name}#{html_path}" if chm_name and html_path else (html_path or chm_name)
                    content_type_val = result.get('content_type', '')
                    ext_val = result.get('extension', '')

                    for ci in range(0, len(content_lines), chunk_sz):
                        chunk_lines = content_lines[ci:ci + chunk_sz]
                        chunk_text = (str(title)[:200] if title else '') + "\n" + "\n".join(chunk_lines)
                        chunk_id = hashlib.md5(f"{path_val}#chunk{ci//chunk_sz}".encode()).hexdigest()[:16]
                        batch_buffer.append(zvec.Doc(
                            id=chunk_id,
                            fields={
                                'chunk_text': chunk_text,
                                'path': str(path_val),
                                'content_type': str(content_type_val),
                                'extension': str(ext_val),
                            }
                        ))

                    processed += 1
                    if len(batch_buffer) >= BATCH_SIZE:
                        col.insert(batch_buffer)
                        col.flush()
                        batch_buffer.clear()
                except Exception:
                    failed += 1

                if self.progress_callback and processed % 50 == 0:
                    pct = (processed / estimated_total * 100) if estimated_total > 0 else 0
                    self.progress_callback(pct, f"{processed}/{estimated_total} files", {"processed": processed, "total": estimated_total})

            # Wait for all worker processes to exit
            for p in workers:
                p.join(timeout=TIMEOUT_DOCUMENT_WORKER_JOIN)
                if p.is_alive():
                    p.terminate()

            # Insert remaining batch
            if batch_buffer:
                col.insert(batch_buffer)
                col.flush()
                batch_buffer.clear()

            # Build FTS full-text index (already built into Schema, but older collections may lack it)
            if processed > 0:
                if self.progress_callback:
                    self.progress_callback(99, "Building full-text index...")
                try:
                    has_fts = any(f.name == "chunk_text" and f.index_param is not None
                                  for f in col.schema.fields)
                    if not has_fts:
                        col.create_index("chunk_text", zvec.FtsIndexParam(tokenizer_name="jieba"))
                    col.optimize()
                except Exception as e:
                    logger.warning(f"Full-text index build failed (search will automatically degrade): {e}")

        finally:
            # Release the ZVec file lock, then merge into kb_dir
            # zvec.Collection has no close() method; use del + gc to release the file lock
            del col
            import gc
            gc.collect()
            import time
            time.sleep(POLL_INTERVAL_AUTOMATION)
            if tmp_zvec_path.exists():
                for item in tmp_zvec_path.iterdir():
                    target = self.kb_dir / item.name
                    if item.is_dir():
                        try:
                            shutil.copytree(str(item), str(target), dirs_exist_ok=True)
                        except Exception:
                            pass
                    else:
                        try:
                            shutil.copy2(str(item), str(target))
                        except Exception:
                            pass
                shutil.rmtree(str(tmp_zvec_path), ignore_errors=True)

        return {
            'total_files': total_files,
            'processed': processed,
            'failed': failed,
            'skipped': skipped,
            'warnings': warnings,
            'install_hints': install_hints
        }
    
    def scan_directory_async(self, directory: str, extensions: Optional[List[str]] = None,
                            max_workers: Optional[int] = None, callback: Optional[Callable] = None,
                            exclude: Optional[List[str]] = None):
        """
        Asynchronously scan documents in a directory (returns immediately, processes in the background)
        
        Args:
            directory: Directory to scan
            extensions: List of file extensions to process
            max_workers: Maximum number of worker processes
            callback: Callback function after completion
        
        Returns:
            Returns immediately; actual processing happens in a background thread
        """
        if self._scanning:
            logger.warning("Scanning is already in progress")
            return

        def _scan_task():
            try:
                self._scanning = True
                result = self.scan_directory(directory, extensions, max_workers, exclude)
                if callback:
                    callback(result)
                if self.progress_callback:
                    self.progress_callback(100, "Scan complete")
            finally:
                self._scanning = False

        self._scan_thread = threading.Thread(target=_scan_task, daemon=True)
        self._scan_thread.start()

        logger.info(f"Asynchronous scan started: {directory}")
    
    def is_scanning(self) -> bool:
        """Check whether scanning is in progress"""
        return self._scanning
    
    def wait_scan_complete(self, timeout: Optional[float] = None) -> bool:
        """
        Wait for scanning to complete
        
        Args:
            timeout: Timeout time (seconds)
        
        Returns:
            Whether it is complete (True=complete, False=timeout)
        """
        if self._scan_thread is None:
            return True
        
        self._scan_thread.join(timeout=timeout)
        return not self._scan_thread.is_alive()
    
    def add_web_document(self, url: str) -> Optional[Dict]:
        """
        Add a web document

        Args:
            url: Web page URL

        Returns:
            Document information or None
        """
        try:
            processor = WebDocumentProcessor()
            result = processor.process_url(url)

            if result:
                title = result.get('title', '')
                content = result.get('content', '')
                # Defensively clean Base64 data URIs
                content = re.sub(
                    r'data:image/[^;]+;base64,[A-Za-z0-9+/=]{100,}',
                    '[Base64 Image]',
                    content
                )

                # Split into chunks by fixed line count and write to ZVec
                content_lines = content.split('\n')
                chunk_size = CHUNK_SIZE_DOCUMENT_LINES
                docs = []
                for ci in range(0, len(content_lines), chunk_size):
                    chunk_lines = content_lines[ci:ci + chunk_size]
                    chunk_text = (str(title)[:200] if title else '') + "\n" + "\n".join(chunk_lines)
                    chunk_id = hashlib.md5(f"{url}#chunk{ci//chunk_size}".encode()).hexdigest()[:16]
                    docs.append(zvec.Doc(
                        id=chunk_id,
                        fields={
                            'chunk_text': chunk_text,
                            'path': str(url),
                            'content_type': str(result.get('content_type', '')),
                            'extension': '.html',
                        }
                    ))

                if docs:
                    # Check whether the ZVec collection already exists (any manifest.* file)
                    import glob as _glob
                    manifest_files = _glob.glob(str(Path(str(self.zvec_dir)) / 'manifest.*'))
                    if manifest_files:
                        col = zvec.open(str(self.zvec_dir))
                    else:
                        # create_and_open requires that the directory does not exist
                        zvec_path = Path(str(self.zvec_dir))
                        if zvec_path.exists():
                            import shutil as _shutil
                            _shutil.rmtree(str(zvec_path), ignore_errors=True)
                        col_schema = zvec.CollectionSchema("documents", fields=[
                            zvec.FieldSchema("chunk_text", zvec.DataType.STRING, index_param=zvec.FtsIndexParam(tokenizer_name="jieba")),
                            zvec.FieldSchema("path", zvec.DataType.STRING),
                            zvec.FieldSchema("content_type", zvec.DataType.STRING),
                            zvec.FieldSchema("extension", zvec.DataType.STRING),
                        ])
                        col = zvec.create_and_open(str(self.zvec_dir), schema=col_schema)
                    col.insert(docs)
                    col.flush()
                    # zvec.Collection has no close() method; use del+gc to release the lock
                    del col
                    import gc
                    gc.collect()
                    import time
                    time.sleep(POLL_INTERVAL_AUTOMATION)

                return result

            return None
        except Exception as e:
            return {'error': str(e)}

    def crawl_website(self,
                      start_url: str,
                      max_pages: int = 100,
                      max_depth: int = 3,
                      domain_filter: Optional[str] = None,
                      url_pattern: Optional[str] = None) -> Dict:
        """
        Breadth-first crawl a website, parse page links, and store them in the ZVec document knowledge base (non-recursive).

        Args:
            start_url: Start URL
            max_pages: Maximum number of pages to crawl
            max_depth: Maximum crawl depth (1 = only crawl direct links from the start page)
            domain_filter: Domain filter; only crawl matching domains (e.g. \"www.postgresql.org\")
            url_pattern: URL pattern filter (e.g. \"/docs/19/\")

        Returns:
            {"success": int, "failed": int, "total": int, "total_size": int}
        """
        processor = WebDocumentProcessor()
        visited: set = set()
        # BFS queue: (url, depth)
        from collections import deque
        queue: deque = deque()
        queue.append((start_url, 0))
        visited.add(start_url)

        success = 0
        failed = 0
        total_size = 0
        import time as _time

        # Ensure the ZVec collection is initialized
        import glob as _glob
        manifest_files = _glob.glob(str(Path(str(self.zvec_dir)) / 'manifest.*'))
        if manifest_files:
            col = zvec.open(str(self.zvec_dir))
        else:
            # create_and_open requires that the directory does not exist
            zvec_path = Path(str(self.zvec_dir))
            if zvec_path.exists():
                import shutil as _shutil
                _shutil.rmtree(str(zvec_path), ignore_errors=True)
            col_schema = zvec.CollectionSchema("documents", fields=[
                zvec.FieldSchema("chunk_text", zvec.DataType.STRING, index_param=zvec.FtsIndexParam(tokenizer_name="jieba")),
                zvec.FieldSchema("path", zvec.DataType.STRING),
                zvec.FieldSchema("content_type", zvec.DataType.STRING),
                zvec.FieldSchema("extension", zvec.DataType.STRING),
            ])
            col = zvec.create_and_open(str(self.zvec_dir), schema=col_schema)

        # Check the FTS index; if it does not exist (older collections may lack it), try to create it
        has_fts = any(f.name == "chunk_text" and f.index_param is not None
                      for f in col.schema.fields)
        if not has_fts:
            logger.warning("The chunk_text field is missing an FTS index; attempting to rebuild")
            try:
                col.create_index("chunk_text", zvec.FtsIndexParam(tokenizer_name="jieba"))
                col.flush()
            except Exception as e:
                logger.error(f"FTS index rebuild failed: {e}")

        try:
            while queue and (success + failed) < max_pages:
                url, depth = queue.popleft()

                # Crawl and process the page
                result = processor.process_url(url)
                if not result:
                    failed += 1
                    continue

                content = result.get('content', '')
                total_size += len(content)

                # Clean Base64
                content = re.sub(
                    r'data:image/[^;]+;base64,[A-Za-z0-9+/=]{100,}',
                    '[Base64 Image]',
                    content
                )

                # Write to ZVec
                title = result.get('title', '')
                content_lines = content.split('\n')
                chunk_size = CHUNK_SIZE_DOCUMENT_LINES
                docs = []
                for ci in range(0, len(content_lines), chunk_size):
                    chunk_lines = content_lines[ci:ci + chunk_size]
                    chunk_text = (str(title)[:200] if title else '') + "\n" + "\n".join(chunk_lines)
                    chunk_id = hashlib.md5(f"{url}#chunk{ci//chunk_size}".encode()).hexdigest()[:16]
                    docs.append(zvec.Doc(
                        id=chunk_id,
                        fields={
                            'chunk_text': chunk_text,
                            'path': str(url),
                            'content_type': str(result.get('content_type', '')),
                            'extension': '.html',
                        }
                    ))

                if docs:
                    col.insert(docs)
                    col.flush()

                success += 1

                # Progress callback
                if self.progress_callback:
                    pct = min(99.0, (success + failed) / max_pages * 100)
                    self.progress_callback(pct, f"Crawling: {success}/{max_pages} pages (depth {depth})")

                # Non-recursive: extract new links from the page only when current depth < max_depth
                if depth < max_depth:
                    # Re-fetch raw HTML to parse links
                    try:
                        import requests
                        headers = {
                            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                        }
                        resp = requests.get(url, headers=headers, timeout=TIMEOUT_NETWORK_REQUEST)
                        resp.encoding = resp.apparent_encoding or 'utf-8'
                        raw_html = resp.text
                    except Exception:
                        raw_html = ''

                    if raw_html:
                        # Extract all href links
                        found_links = re.findall(r'href="([^"]*)"', raw_html)
                        found_links += re.findall(r"href='([^']*)'", raw_html)

                        for link in found_links:
                            # Skip anchors and non-HTTP(S) protocols
                            if link.startswith('#') or link.startswith('mailto:') or link.startswith('javascript:'):
                                continue

                            # Use urljoin to uniformly complete relative paths in all formats
                            # Including "preface.html", "/docs/19/sql.html", "../../manual", etc.
                            from urllib.parse import urljoin as _urljoin
                            full_url = _urljoin(url, link)
                            if not full_url.startswith('http'):
                                continue

                            # Domain filtering
                            if domain_filter and domain_filter not in full_url:
                                continue
                            # URL pattern filtering
                            if url_pattern and url_pattern not in full_url:
                                continue
                            # Deduplicate
                            clean_link = full_url.split('#')[0]
                            if clean_link not in visited:
                                visited.add(clean_link)
                                queue.append((clean_link, depth + 1))

                # Polite delay
                _time.sleep(POLL_INTERVAL_AUTOMATION)

        finally:
            # Optimize index
            try:
                col.optimize()
                col.flush()
            except Exception:
                pass
            del col
            import gc
            gc.collect()

        return {
            'success': success,
            'failed': failed,
            'total': success + failed,
            'total_size': total_size,
        }

    def search(self, query: str, content_type: Optional[str] = None, top_k: int = 10, use_fts5: bool = True) -> List[Dict]:
        """
        Search documents (using ZVec full-text search)

        Args:
            query: Search keywords
            content_type: Document type filter
            top_k: Number of returned results
            use_fts5: Compatibility parameter, deprecated

        Returns:
            List of matching documents
        """
        try:
            col = zvec.open(str(self.zvec_dir))
            results = col.query(
                zvec.Query(field_name="chunk_text", fts=zvec.Fts(match_string=query)),
                topk=top_k * 2,
            )

            formatted = []
            seen_paths = set()
            for r in results:
                path_val = r.fields.get('path', '')
                # Deduplicate: keep only the highest-scoring result for the same path
                if path_val in seen_paths:
                    continue
                seen_paths.add(path_val)

                chunk_text = r.fields.get('chunk_text', '')
                doc_entry = {
                    'path': path_val,
                    'full_path': path_val,
                    'title': '',
                    'content': chunk_text,
                    'content_type': r.fields.get('content_type', ''),
                    'extension': r.fields.get('extension', ''),
                    'score': r.score or 0,
                }
                # Extract title from first line of chunk_text
                first_newline = chunk_text.find('\n')
                if first_newline > 0:
                    doc_entry['title'] = chunk_text[:first_newline].strip()
                formatted.append(doc_entry)

                if len(formatted) >= top_k:
                    break

            if content_type and formatted:
                formatted = [r for r in formatted if r.get('content_type') == content_type]
            return formatted[:top_k]
        except Exception as e:
            logger.warning(f"ZVec search failed: {e}")
            return []

    def get_statistics(self) -> Dict:
        """Get statistics (based on ZVec)"""
        try:
            col = zvec.open(str(self.zvec_dir))
            total_documents = col.stats.doc_count

            # Count by extension / content_type (requires FTS query; skip distribution if it fails)
            ext_stats = {}
            type_stats = {}
            if total_documents > 0:
                try:
                    all_docs = col.query(
                        zvec.Query(field_name="chunk_text", fts=zvec.Fts(query_string="*")),
                        topk=min(total_documents, 5000),
                    )
                    for d in all_docs:
                        ext = d.fields.get('extension', '(no ext)')
                        ext_stats[ext] = ext_stats.get(ext, 0) + 1

                    for d in all_docs:
                        ct = d.fields.get('content_type', 'unknown')
                        type_stats[ct] = type_stats.get(ct, 0) + 1
                except Exception:
                    pass  # Return empty distribution if distribution statistics fail

            return {
                'total_documents': total_documents,
                'by_type': type_stats,
                'by_extension': ext_stats,
                'database_size_mb': 0,
                'last_build_time': None,
                'last_build_duration': None,
            }
        except Exception as e:
            logger.warning(f"Failed to get ZVec statistics: {e}")
            return {'total_documents': 0, 'by_type': {}, 'by_extension': {}, 'database_size_mb': 0}