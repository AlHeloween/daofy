"""
File backup utility — __history backup/restore/list

Provides a Delphi IDE-compatible __history backup mechanism.
Backup file naming: filename.~version~ (e.g. Unit.pas.~1~)
Old backups older than RETENTION_DAYS days are automatically cleaned up.
"""

import os
import shutil
import statistics
import time
from typing import Optional, List, Dict
from .logger import get_logger

logger = get_logger(__name__)

# Backup retention policy: when count exceeds this and backups are older than retention days, oldest backups are pruned
MAX_BACKUPS = 20
RETENTION_DAYS = 7

# Large-file copy buffer size (1MB) — shutil.copyfileobj defaults to 16KB
# 64x buffer = 64x fewer syscalls for the same I/O
_COPY_BUF_SIZE = 1024 * 1024

# Full-file encoding detection limit: above this size (not source text) degrade to multi-point sampling,
# avoiding reading hundreds of MB at once and causing memory spikes
_MAX_FULL_DETECT_BYTES = 32 * 1024 * 1024

# UTF-16 no-BOM heuristic analysis window: null byte distribution is structural (content-independent),
# first 1MB is enough, avoiding building million-entry null position lists for huge files
_UTF16_ANALYSIS_WINDOW = 1024 * 1024

# Accept only multibyte CJK encodings when chardet confidence is low; single-byte encodings (cp1252 etc.)
# accept arbitrary bytes and never error, causing misdetection, so they are not accepted
_CHARDET_MULTIBYTE = {
    'big5', 'shift_jis', 'cp932', 'euc-kr', 'cp949',
    'euc-jp', 'iso-2022-jp', 'iso-2022-kr',
}


def _fast_copy(src: str, dst: str) -> None:
    """
    Fast file copy using a large buffer (preserves metadata).

    shutil.copy2 internally uses shutil.copyfileobj's default 16KB buffer,
    generating many syscalls for large files. This function uses a 1MB buffer
    to reduce syscall count by 64x.

    Args:
        src: source file path
        dst: destination file path
    """
    with open(src, 'rb') as fsrc:
        with open(dst, 'wb') as fdst:
            shutil.copyfileobj(fsrc, fdst, _COPY_BUF_SIZE)
    shutil.copystat(src, dst)


def _normalize_charset_name(enc: str) -> str:
    """Normalize charset name to project standard name"""
    # chardet returns: GB2312, Shift_JIS, EUC-KR, ISO-2022-JP, Big5...
    # locale returns: cp1252, gbk, big5, cp932, cp949...
    # Normalize to lowercase + remove hyphens before lookup
    key = enc.lower().replace('-', '')
    norms = {
        'utf8': 'utf-8',
        'utf8sig': 'utf-8-sig',
        'utf16le': 'utf-16-le',
        'utf16be': 'utf-16-be',
        'utf16': 'utf-16',
        'ascii': 'utf-8',
        'latin1': 'utf-8',
        'iso88591': 'utf-8',
        'gb2312': 'gbk',
        'gb18030': 'gbk',   # GB18030 is a superset of GBK, uniformly mapped to gbk
        'cp936': 'gbk',
        'hzgb2312': 'gbk',
        'big5hkscs': 'big5',
        'cp950': 'big5',
        'ms932': 'cp932',
        'shiftjis': 'shift_jis',
        'euckr': 'euc-kr',
        'cp949': 'cp949',
        'ksc56011987': 'cp949',  # ks_c_5601_1987 after removing hyphens and underscores
        'eucjp': 'euc-jp',
        'iso2022jp': 'iso-2022-jp',
        'iso2022kr': 'iso-2022-kr',
    }
    if key in norms:
        return norms[key]
    # Try again after removing underscores (compatible with underscored formats)
    key_flat = key.replace('_', '')
    if key_flat in norms:
        return norms[key_flat]
    return key


def _read_sample_for_detection(f, file_size: int) -> bytes:
    """
    Multi-point sampling for very large files (>32MB): start + 1/3 + 2/3 + end, total cap 256KB.

    Args:
        f: opened binary file handle (positioned at file start)
        file_size: total file size in bytes

    Returns:
        Sampled byte string
    """
    chunk = 16384
    max_total = 262144
    parts = []
    total_read = 0

    # Start
    parts.append(f.read(chunk))
    total_read += chunk

    # 1/3 position
    f.seek(max(0, file_size // 3 - chunk // 2))
    d = f.read(chunk)
    parts.append(d)
    total_read += len(d)

    if total_read < max_total:
        # 2/3 position
        f.seek(max(0, file_size * 2 // 3 - chunk // 2))
        d = f.read(chunk)
        parts.append(d)
        total_read += len(d)

    if total_read < max_total:
        # End
        f.seek(max(0, file_size - chunk))
        d = f.read(chunk)
        parts.append(d)
        total_read += len(d)

    return b''.join(parts)[:max_total]


def _chardet_fallback(raw_data: bytes) -> Optional[str]:
    """
    chardet fallback detection: called only when full-file UTF-8 and GBK both fail to decode.

    High confidence (>0.7) is accepted directly (after normalization); low confidence accepts only
    multibyte CJK encodings (big5/shift_jis/euc-kr etc.) to avoid single-byte encoding misdetection.

    Args:
        raw_data: raw file bytes

    Returns:
        Normalized encoding name; None if unrecognized
    """
    try:
        import chardet
        result = chardet.detect(raw_data)
        enc = result.get('encoding')
        conf = result.get('confidence', 0)
        if not enc or conf <= 0:
            return None
        norm = _normalize_charset_name(enc)
        if conf > 0.7:
            return norm
        if norm in _CHARDET_MULTIBYTE:
            return norm
    except Exception:
        logger.debug("chardet detection failed, degrading to default encoding gbk")
    return None


def detect_encoding(file_path: str) -> str:
    """
    Detect file encoding.

    Detection order: BOM → no-BOM UTF-16 heuristic → full UTF-8 → full GBK → chardet fallback

    - BOM detection: UTF-8 BOM → utf-8-sig; UTF-16 BOM → utf-16
    - No-BOM UTF-16 heuristic: null byte distribution (first 1MB window) + full decode verification
    - No-BOM text determination (full-file detection, no longer 4K/multi-point sampling):
      full file contains valid UTF-8 sequence → utf-8 (no BOM); otherwise full file decodes as GBK → gbk
    - chardet fallback: when both UTF-8 and GBK decoding fail (encoding anomalies/binary/rare multibyte encodings)
      identify big5/shift_jis/euc-kr etc.; if still failing default gbk

    Note: after full-file determination, most Big5/Shift-JIS/EUC-KR files can decode as GBK and are judged
    gbk (expected behavior in mainland scenarios); chardet participates only as fallback when both UTF-8/GBK fail.

    Args:
        file_path: file path

    Returns:
        Encoding name (utf-8 / utf-8-sig / utf-16 / utf-16-le / utf-16-be
        / gbk / big5 / shift_jis / euc-kr / euc-jp etc.)
    """
    try:
        file_size = os.path.getsize(file_path)

        # ── Full-file read ──
        # Front sampling (4K/multi-point) is unsafe for files that are "pure ASCII at the front, CJK at the back",
        # so always read the full file for determination; only non-source files over 32MB degrade to multi-point sampling.
        with open(file_path, 'rb') as f:
            if file_size <= _MAX_FULL_DETECT_BYTES:
                raw_data = f.read()
            else:
                raw_data = _read_sample_for_detection(f, file_size)

        if not raw_data:
            return 'utf-8'

        # ── 1. BOM detection ──
        if raw_data.startswith(b'\xff\xfe') or raw_data.startswith(b'\xfe\xff'):
            return 'utf-16'
        if raw_data.startswith(b'\xef\xbb\xbf'):
            return 'utf-8-sig'

        # ── 2. No-BOM UTF-16 heuristic detection ──
        # Reason: ASCII-style UTF-16 no-BOM files ("u\0n\0i\0t\0...") can decode as
        # UTF-8 (containing NUL) and must be checked before UTF-8 determination, otherwise they would be misjudged as utf-8.
        # Null byte distribution is a structural feature; first 1MB window is sufficient; decode verifies full file.
        if len(raw_data) >= 8 and len(raw_data) % 2 == 0:
            sample = raw_data[:min(len(raw_data), _UTF16_ANALYSIS_WINDOW)]

            # Find positions of all null bytes
            null_positions = [i for i, b in enumerate(sample) if b == 0]

            if len(null_positions) >= 4:
                # Compute gaps between adjacent null bytes
                gaps = [null_positions[i + 1] - null_positions[i]
                        for i in range(len(null_positions) - 1)]

                median_gap = statistics.median(gaps)
                gap_range = max(gaps) - min(gaps)
                mean_gap = statistics.mean(gaps)
                # Gap consistency: smaller is more regular. UTF-16 null gaps cluster around 2
                gap_consistency = gap_range / mean_gap if mean_gap > 0 else 0
                # Small-gap ratio: tolerate gaps interrupted by CJK segments (e.g. "unit Test;\n// Chinese...")
                # Text-like encodings (utf-8/gbk/big5 etc.) almost never contain NUL; data dense with nulls
                # and concentrated in a single parity position is almost certainly UTF-16, so relaxing consistency is safe.
                small_gap_ratio = (
                    sum(1 for g in gaps if g <= 3) / len(gaps)
                    if gaps else 0.0
                )

                # Compute odd/even null distribution
                odd_nulls = sum(1 for p in null_positions if p % 2 == 1)
                even_nulls = len(null_positions) - odd_nulls

                # UTF-16-LE: nulls concentrated at odd positions, gap ≈ 2, regular distribution
                if (odd_nulls > even_nulls * 3
                        and median_gap <= 2.5
                        and (gap_consistency < 3.0 or small_gap_ratio >= 0.75)):
                    try:
                        raw_data.decode('utf-16-le')
                        return 'utf-16-le'
                    except (UnicodeDecodeError, ValueError):
                        pass

                # UTF-16-BE: nulls concentrated at even positions
                if (even_nulls > odd_nulls * 3
                        and median_gap <= 2.5
                        and (gap_consistency < 3.0 or small_gap_ratio >= 0.75)):
                    try:
                        raw_data.decode('utf-16-be')
                        return 'utf-16-be'
                    except (UnicodeDecodeError, ValueError):
                        pass

        # ── 3. Full UTF-8 determination: valid UTF-8 sequence exists → UTF-8 no BOM ──
        try:
            raw_data.decode('utf-8')
            return 'utf-8'
        except UnicodeDecodeError:
            pass

        # ── 4. Full GBK determination: not UTF-8 → GBK ──
        try:
            raw_data.decode('gbk')
            return 'gbk'
        except UnicodeDecodeError:
            pass

        # ── 5. chardet fallback ──
        # Triggered only when both UTF-8 and GBK fail to decode (encoding anomaly/binary/rare multibyte encodings);
        # if still failing, default gbk.
        guess = _chardet_fallback(raw_data)
        if guess:
            return guess

        return 'gbk'

    except Exception as e:
        logger.warning(f"Failed to detect file encoding: {e}, using default encoding utf-8")
        return 'utf-8'


def _prune_backups(history_dir: str, base_name: str) -> None:
    """
    Prune old backups according to policy: when more than MAX_BACKUPS exist, remove those beyond the limit
    that are older than RETENTION_DAYS. When fewer than MAX_BACKUPS exist, keep all.

    Args:
        history_dir: __history directory path
        base_name: file name (e.g. Unit.pas)
    """
    try:
        # Collect all valid backups and sort by version number descending
        backups = []
        for f in os.listdir(history_dir):
            if not (f.startswith(f"{base_name}.~") and f.endswith("~")):
                continue
            try:
                ver = int(f[len(base_name) + 2:-1])
                path = os.path.join(history_dir, f)
                mtime = os.path.getmtime(path)
                backups.append((ver, path, mtime))
            except (ValueError, IndexError, OSError):
                continue

        if len(backups) <= MAX_BACKUPS:
            return

        # Sort by version descending, keep the newest MAX_BACKUPS
        backups.sort(key=lambda x: x[0], reverse=True)
        protected = set(backups[:MAX_BACKUPS])
        cutoff = time.time() - RETENTION_DAYS * 86400

        for ver, path, mtime in backups[MAX_BACKUPS:]:
            if mtime < cutoff:
                try:
                    os.remove(path)
                    logger.debug(f"Cleaned expired backup: {path} (version {ver}, {RETENTION_DAYS} days ago)")
                except OSError:
                    pass
    except Exception as e:
        logger.warning(f"Failed to clean old backups: {e}")


def create_backup(file_path: str) -> Optional[str]:
    """
    Create a __history backup file.

    Create a __history subdirectory in the source file's directory and generate a backup with an incrementing version number.
    Version number format: filename.~N~ (compatible with Delphi IDE)

    Args:
        file_path: source file path

    Returns:
        Backup file path, or None on failure
    """
    try:
        if not os.path.isfile(file_path):
            logger.warning(f"Backup failed, file does not exist: {file_path}")
            return None

        file_dir = os.path.dirname(os.path.abspath(file_path))
        history_dir = os.path.join(file_dir, "__history")
        os.makedirs(history_dir, exist_ok=True)

        base_name = os.path.basename(file_path)

        # Find existing backups and determine the new version number
        backup_files = [
            f for f in os.listdir(history_dir)
            if f.startswith(f"{base_name}.~") and f.endswith("~")
        ]

        max_version = 0
        for backup_file in backup_files:
            try:
                version_str = backup_file[len(base_name) + 2:-1]  # Strip "filename.~" and "~"
                version = int(version_str)
                if version > max_version:
                    max_version = version
            except (ValueError, IndexError):
                continue

        # Increment version number; if target path is already occupied (e.g. version conflict due to junk files), keep incrementing
        new_version = max_version + 1
        while True:
            backup_path = os.path.join(history_dir, f"{base_name}.~{new_version}~")
            if not os.path.exists(backup_path):
                break
            new_version += 1

        _fast_copy(file_path, backup_path)
        logger.info(f"Created backup file: {backup_path}")

        # Clean up old backups beyond the limit
        _prune_backups(history_dir, base_name)

        return backup_path

    except Exception as e:
        logger.warning(f"Failed to create backup file: {e}")
        return None


def list_backups(file_path: str) -> List[Dict]:
    """
    List all backup versions of the specified file.

    Args:
        file_path: source file path

    Returns:
        List of backup versions, each containing version, path, size, mtime fields.
        Sorted by version number descending (newest first).
    """
    file_dir = os.path.dirname(os.path.abspath(file_path))
    history_dir = os.path.join(file_dir, "__history")

    if not os.path.isdir(history_dir):
        return []

    base_name = os.path.basename(file_path)
    backups = []

    for f in os.listdir(history_dir):
        if not (f.startswith(f"{base_name}.~") and f.endswith("~")):
            continue

        full_path = os.path.join(history_dir, f)
        try:
            version_str = f[len(base_name) + 2:-1]
            version = int(version_str)
            stat = os.stat(full_path)
            backups.append({
                "version": version,
                "path": full_path,
                "size": stat.st_size,
                "mtime": stat.st_mtime,
            })
        except (ValueError, OSError):
            continue

    backups.sort(key=lambda x: x["version"], reverse=True)
    return backups


def restore_backup(file_path: str, version: Optional[int] = None) -> Optional[str]:
    """
    Restore a file to the specified version from __history.

    Args:
        file_path: source file path
        version: version number; uses the latest version if not provided

    Returns:
        Restored backup file path, or None on failure
    """
    backups = list_backups(file_path)
    if not backups:
        logger.warning(f"Restore failed, no backup files found: {file_path}")
        return None

    if version is not None:
        target = next((b for b in backups if b["version"] == version), None)
        if not target:
            logger.warning(f"Restore failed, version {version} not found, available versions: {[b['version'] for b in backups]}")
            return None
    else:
        target = backups[0]  # latest version

    try:
        # Back up the current file before restoring (safety net)
        create_backup(file_path)

        _fast_copy(target["path"], file_path)
        logger.info(f"Restored from backup: {target['path']} → {file_path}")
        return target["path"]

    except Exception as e:
        logger.error(f"Failed to restore backup: {e}")
        return None

