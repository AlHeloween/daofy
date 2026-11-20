"""
Document knowledge base helpers.
Backs the document actions of the delphi_kb tool.
"""

from typing import Any
from mcp.types import CallToolResult
from pathlib import Path

from ..services.knowledge_base.scan_generic_documents import (
    GenericDocumentScanner,
    WebDocumentProcessor
)


_doc_scanner = None


def _get_scanner() -> GenericDocumentScanner:
    """Return the document scanner instance."""
    global _doc_scanner
    
    if _doc_scanner is None:
        server_root = Path(__file__).parent.parent.parent
        kb_dir = str(server_root / "data" / "document-knowledge-base")
        
        kb_path = Path(kb_dir)
        kb_path.mkdir(parents=True, exist_ok=True)
        
        _doc_scanner = GenericDocumentScanner(kb_dir)
    
    return _doc_scanner


async def scan_documents(arguments: Any) -> CallToolResult:
    """Scan the documents in a directory."""
    directory = arguments.get("directory")
    extensions = arguments.get("extensions")
    max_workers = arguments.get("max_workers")
    
    if not directory:
        return CallToolResult(
            content=[{"type": "text", "text": "The directory parameter is required"}],
            isError=True
        )
    
    dir_path = Path(directory)
    if not dir_path.exists():
        return CallToolResult(
            content=[{"type": "text", "text": f"Directory does not exist: {directory}"}],
            isError=True
        )
    
    scanner = _get_scanner()
    result = scanner.scan_directory(
        directory=directory,
        extensions=extensions,
        max_workers=max_workers
    )
    
    if 'error' in result:
        return CallToolResult(
            content=[{"type": "text", "text": f"Scan failed: {result['error']}"}],
            isError=True
        )
    
    output = f"Document scan complete:\n"
    output += f"  Total files: {result['total_files']}\n"
    output += f"  Processed: {result['processed']}\n"
    output += f"  Failed: {result['failed']}\n"
    
    stats = scanner.get_statistics()
    if stats.get('by_type'):
        output += f"\nCounts by type:\n"
        for content_type, count in stats['by_type'].items():
            output += f"  {content_type}: {count}\n"
    
    return CallToolResult(content=[{"type": "text", "text": output}])


async def add_web_document(arguments: Any) -> CallToolResult:
    """Add a web document."""
    url = arguments.get("url")
    
    if not url:
        return CallToolResult(
            content=[{"type": "text", "text": "The url parameter is required"}],
            isError=True
        )
    
    if not url.startswith(('http://', 'https://')):
        return CallToolResult(
            content=[{"type": "text", "text": "URL must start with http:// or https://"}],
            isError=True
        )
    
    scanner = _get_scanner()
    result = scanner.add_web_document(url)
    
    if result is None:
        return CallToolResult(
            content=[{"type": "text", "text": f"Failed to add web document: {url}"}],
            isError=True
        )
    
    if isinstance(result, dict) and 'error' in result:
        return CallToolResult(
            content=[{"type": "text", "text": f"Failed to add web document: {result['error']}"}],
            isError=True
        )
    
    output = f"Web document added:\n"
    output += f"  Title: {result.get('title', 'N/A')}\n"
    output += f"  URL: {url}\n"
    output += f"  Size: {result.get('size', 0)} bytes\n"
    output += f"  Lines: {result.get('line_count', 0)}\n"
    output += f"  Sections: {len(result.get('sections', []))}\n"
    output += f"  Code blocks: {len(result.get('code_examples', []))}\n"
    
    return CallToolResult(content=[{"type": "text", "text": output}])


async def search_documents(arguments: Any) -> CallToolResult:
    """Search the documents."""
    query = arguments.get("query")
    content_type = arguments.get("content_type")
    top_k = min(arguments.get("top_k", 200), 500)
    
    if not query:
        return CallToolResult(
            content=[{"type": "text", "text": "The query parameter is required"}],
            isError=True
        )
    
    scanner = _get_scanner()
    results = scanner.search(query, content_type=content_type, top_k=top_k)
    
    if not results:
        msg = f"No document matched '{query}'"
        
        import re
        if re.search(r'[\u4e00-\u9fff]', query):
            # Chinese query — inspect the document library's languages
            stats = scanner.get_statistics()
            languages = stats.get('by_language', {})
            total = stats.get('total_documents', 0)
            
            # Build the language hint
            lang_hints = []
            if languages.get('en', 0) > 0:
                pct = languages['en'] / total * 100
                lang_hints.append(f"English ({pct:.0f}%)")
            if languages.get('ja', 0) > 0:
                pct = languages['ja'] / total * 100
                lang_hints.append(f"Japanese ({pct:.0f}%)")
            if languages.get('ko', 0) > 0:
                pct = languages['ko'] / total * 100
                lang_hints.append(f"Korean ({pct:.0f}%)")
            
            if lang_hints:
                msg += f"\n\n💡 Document library contains: {', '.join(lang_hints)}"
                msg += "\n   The AI can translate the keyword and retry, for example:"
                msg += "\n   - '创建表' → 'CREATE TABLE'"
                msg += "\n   - '索引语法' → 'CREATE INDEX'"
        
        return CallToolResult(content=[{"type": "text", "text": msg}])
    
    output = f"Search '{query}'"
    if content_type:
        output += f" (type: {content_type})"
    output += f" — {len(results)} result(s):\n\n"
    
    for i, doc in enumerate(results, 1):
        doc_id = doc.get('id')
        output += f"{i}. [ID:{doc_id}] {doc.get('title', 'N/A')}\n"
        output += f"   Type: {doc.get('content_type', 'N/A')}\n"
        
        if doc.get('url'):
            output += f"   URL: {doc.get('url')}\n"
        else:
            output += f"   Path: {doc.get('path', 'N/A')}\n"
        
        output += f"   Size: {doc.get('size', 0)} bytes\n"
        
        content = doc.get('content', '')
        if content:
            preview = content[:200].replace('\n', ' ')
            output += f"   Preview: {preview}...\n"
        
        output += "\n"
    
    output += f"Hint: use delphi_kb(action=read, doc_id={results[0].get('id')}) to read the full content\n"
    
    return CallToolResult(content=[{"type": "text", "text": output}])


async def get_document_statistics(arguments: Any) -> CallToolResult:
    """Return the document statistics."""
    scanner = _get_scanner()
    stats = scanner.get_statistics()
    
    output = "Document KB statistics:\n"
    output += f"  Total documents: {stats.get('total_documents', 0)}\n\n"
    
    by_type = stats.get('by_type', {})
    if by_type:
        output += "Counts by type:\n"
        for content_type, count in by_type.items():
            output += f"  {content_type}: {count}\n"
        output += "\n"
    
    by_extension = stats.get('by_extension', {})
    if by_extension:
        output += "Counts by extension:\n"
        for ext, count in sorted(by_extension.items(), key=lambda x: x[1], reverse=True):
            output += f"  {ext}: {count}\n"
    
    return CallToolResult(content=[{"type": "text", "text": output}])


async def read_document(arguments: Any) -> CallToolResult:
    """Read document content (ZVec-backed)."""
    import zvec

    url = arguments.get("url")
    doc_id = arguments.get("doc_id")
    offset = arguments.get("offset", 0)
    limit = arguments.get("limit", 5000)

    if not url and not doc_id:
        return CallToolResult(
            content=[{"type": "text", "text": "The url or doc_id parameter is required"}],
            isError=True
        )

    scanner = _get_scanner()
    kb_dir = scanner.zvec_dir

    try:
        col = zvec.open(str(kb_dir))
        search_field = "path" if not doc_id else "path"
        search_term = doc_id if doc_id else url
        results = col.search(search_field, search_term, zvec.FtsParams(top_k=100))

        if not results:
            # Retry the search on the url field
            results = col.search("path", url or "", zvec.FtsParams(top_k=100))

        if not results:
            col.close()
            return CallToolResult(
                content=[{"type": "text", "text": f"Document not found: {url or doc_id}"}],
                isError=True
            )

        # Merge all chunks of the same path
        title = results[0].get('chunk_text', '')[:80]
        content_parts = []
        for r in results:
            chunk_text = r.get('chunk_text', '')
            first_nl = chunk_text.find('\n')
            if first_nl >= 0:
                content_parts.append(chunk_text[first_nl + 1:])
            else:
                content_parts.append(chunk_text)

        full_content = "\n".join(content_parts)
        col.close()

        content_len = len(full_content)
        if offset < 0:
            offset = 0
        if limit > 20000:
            limit = 20000

        content_slice = full_content[offset:offset + limit]

        output = f"Document: {title}\n"
        output += f"Path: {url or doc_id}\n"
        output += f"Content length: {content_len} characters\n"
        output += f"Showing: {offset} - {offset + len(content_slice)}\n"
        output += "=" * 60 + "\n\n"
        output += content_slice

        if offset + limit < content_len:
            remaining = content_len - (offset + limit)
            output += f"\n... ({remaining} characters not shown) ...\n"
            output += f"Hint: use offset={offset + limit} to continue reading\n"

        return CallToolResult(content=[{"type": "text", "text": output}])
    except Exception as e:
        return CallToolResult(
            content=[{"type": "text", "text": f"Failed to read document: {str(e)}"}],
            isError=True
        )
