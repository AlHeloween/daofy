"""
Project knowledge base service

Copyright (C) Jilin Zuoyou Software Development Co., Ltd.
Copyright (C) Equilibrium Software Development Co., Ltd, Jilin
Update & Mod By Crystalxp (Dark Night Killer QQ:281309196)

Provides knowledge base functionality for user projects:
1. Read third-party library directories from .dproj files and build knowledge base
2. Build knowledge base for project source code, supporting incremental updates
3. Support .dproj/.dpr/.dpk project file types (only .dproj can extract third-party library paths)
"""

import os
import json
import time
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Set, Callable
from src.constants import DIR_DELPHI_KB, REG_KEY_EMBARCADERO_BDS, SOURCE_SCAN_EXCLUDED_DIRS
from src.utils.logger import get_logger
from src.utils.dproj_parser import DprojParser
from .delphi_chunker import chunk_file_list
from .zvec_adapter import ZVecKnowledgeBaseAdapter

logger = get_logger(__name__)


class ProjectKnowledgeBase:
    """Project knowledge base manager (ZVec version)"""

    def __init__(self, project_path: str, progress_callback: Optional[Callable] = None):
        """
        Initialize project knowledge base

        Args:
            project_path: Project file path (.dproj / .dpr / .dpk)
            progress_callback: Progress callback function
        """
        self.project_path = Path(project_path)
        self.project_dir = self.project_path.parent
        self.project_name = self.project_path.stem
        self.progress_callback = progress_callback

        # Project knowledge base directory
        self.kb_dir = self.project_dir / DIR_DELPHI_KB
        self.kb_dir.mkdir(parents=True, exist_ok=True)

        # ZVec knowledge base adapter
        self.project_kb: Optional[ZVecKnowledgeBaseAdapter] = None
        self.thirdparty_kb: Optional[ZVecKnowledgeBaseAdapter] = None

        logger.info(f"Project knowledge base initialized: {self.project_name}")

    def _get_delphi_install_paths(self) -> Set[str]:
        """
        Get Delphi installation path list

        Returns:
            Set of Delphi installation paths
        """
        delphi_paths = set()

        try:
            import winreg

            # Open Delphi registry key
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY_EMBARCADERO_BDS)

            # Iterate over all versions
            i = 0
            while True:
                try:
                    version_key = winreg.EnumKey(key, i)
                    i += 1

                    # Get version info
                    version_path = winreg.OpenKey(key, version_key)
                    try:
                        root_dir = winreg.QueryValueEx(version_path, "RootDir")[0]
                        if root_dir:
                            # Add Delphi installation path and its subdirectories
                            delphi_paths.add(Path(root_dir).resolve())
                    except OSError:
                        pass
                    finally:
                        winreg.CloseKey(version_path)

                except WindowsError:
                    break

            winreg.CloseKey(key)

        except Exception as e:
            logger.warning(f"Failed to get Delphi installation paths: {e}")

        return delphi_paths

    def get_thirdparty_paths_from_dproj(self) -> List[str]:
        """
        Extract third-party library paths from .dproj file

        Returns:
            List of third-party library paths
        """
        if self.project_path.suffix.lower() != '.dproj':
            logger.debug("Project file is not in .dproj format (%s), skipping third-party library path extraction", self.project_path.suffix)
            return []

        parser = DprojParser(str(self.project_path))
        if not parser.parse():
            logger.error("Failed to parse .dproj file")
            return []

        # Get unit search paths
        unit_paths = parser.get_unit_search_paths()

        # Get Delphi installation paths (for exclusion)
        delphi_install_paths = self._get_delphi_install_paths()

        # Filter out third-party library paths (exclude project's own directory and Delphi installation directory)
        thirdparty_paths = []
        for path in unit_paths:
            path_obj = Path(path)

            # Check if path exists
            if not path_obj.exists():
                continue

            # Resolve to absolute path
            path_obj = path_obj.resolve()

            # Check if under Delphi installation directory
            is_delphi_path = False
            for delphi_path in delphi_install_paths:
                try:
                    path_obj.relative_to(delphi_path)
                    is_delphi_path = True
                    break
                except ValueError:
                    pass

            if is_delphi_path:
                # Skip paths under Delphi installation directory
                continue

            # Check if outside project directory
            try:
                # Relative path check
                path_obj.relative_to(self.project_dir)
            except ValueError:
                # Outside project directory, it is a third-party library
                thirdparty_paths.append(str(path_obj))
            else:
                # Inside project directory, check if it is a common third-party library directory name
                path_lower = str(path_obj).lower()
                thirdparty_keywords = ['thirdpart', 'thirdparty', 'vendor', 'lib', 'libs', 'packages', 'components']
                if any(kw in path_lower for kw in thirdparty_keywords):
                    thirdparty_paths.append(str(path_obj))

        logger.info(f"Extracted {len(thirdparty_paths)} third-party library paths from .dproj")
        return thirdparty_paths

    def _calculate_paths_hash(self, paths: List[str]) -> str:
        """Calculate signature of path list (sort and join with semicolons, no MD5 needed)"""
        return ";".join(sorted(paths))

    def _calculate_source_hash(self, source_dir: Path, extensions: Set[str] = None) -> str:
        """
        Calculate change signature of source directory (based on file count + total size + latest modification time)

        Skip third-party library paths and .delphi-kb directory to avoid treating changes in KB itself or third-party libraries
        as project source changes, while greatly speeding up calculation.

        Use `file count|total bytes|latest mtime` triple instead of MD5 hash because:
        - No need to calculate MD5 per file (high IO + CPU overhead)
        - Changes in file count/total size/latest time cover all add/delete/modify scenarios
        - Only when hash_mode=md5 is specified in config.json is per-file MD5 needed

        Args:
            source_dir: Source directory
            extensions: Set of file extensions

        Returns:
            Signature value (file count|total size|latest modification time)
        """
        if extensions is None:
            extensions = {'.pas', '.dpr', '.dpk', '.dfm', '.fmx', '.inc'}

        # Directory names to skip (third-party libraries, knowledge base, system directories, etc.)
        skip_dir_names = SOURCE_SCAN_EXCLUDED_DIRS

        # Read third-party library path prefixes verified by .dproj, skip precisely
        # (Only skip directories that appear in both shared KB and .dproj third-party library paths,
        #  to avoid project source directories being mistakenly skipped because they accidentally appear in IDE global library paths)
        skip_paths_normalized = self._get_verified_thirdparty_prefixes()

        total_files = 0
        total_size = 0
        latest_mtime = 0.0

        for root, dirs, files in os.walk(source_dir):
            # Skip unneeded directories (do not traverse into them)
            dirs[:] = [d for d in dirs if d.lower() not in skip_dir_names]

            root_normalized = str(Path(root).resolve())
            if root_normalized in skip_paths_normalized:
                dirs[:] = []
                continue

            for file in files:
                if Path(file).suffix.lower() in extensions:
                    try:
                        stat = (Path(root) / file).stat()
                        total_files += 1
                        total_size += stat.st_size
                        if stat.st_mtime > latest_mtime:
                            latest_mtime = stat.st_mtime
                    except Exception as e:
                        logger.debug("Ignoring non-fatal exception: %s", str(e))

        return f"{total_files}|{total_size}|{latest_mtime}"

    def _get_shared_thirdparty_paths(self) -> Set[str]:
        """
        Read the list of scanned paths from the MCP server shared third-party knowledge base.

        Shared knowledge base path:
          <project root>/data/thirdparty-knowledge-base/thirdparty_paths.json

        Returns:
            Set of scanned paths (absolute paths, normalized)
        """
        # Derive project root from current file location: src/services/know_base/ → up 3 levels = project root
        _project_root = Path(__file__).parent.parent.parent.parent
        shared_paths_file = (
            _project_root / "data" / "thirdparty-knowledge-base" / "thirdparty_paths.json"
        )
        if not shared_paths_file.exists():
            logger.info("Shared third-party knowledge base path file does not exist, skipping check")
            return set()

        try:
            with open(shared_paths_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            raw_paths = data.get("paths", [])
            # Normalize all paths (resolve real case)
            normalized = set()
            for p in raw_paths:
                try:
                    normalized.add(str(Path(p).resolve()))
                except Exception:
                    normalized.add(p)
            logger.info(f"Read {len(normalized)} scanned paths from shared knowledge base")
            return normalized
        except Exception as e:
            logger.warning(f"Failed to read shared third-party knowledge base paths: {e}")
            return set()

    def _get_verified_thirdparty_prefixes(self) -> Set[str]:
        """
        Get the set of verified third-party library path prefixes.

        Only return paths that **simultaneously satisfy** the following conditions:
        1. Appear in shared knowledge base thirdparty_paths.json
        2. Are inside project directory (under self.project_dir)
        3. Are also recognized as third-party library paths by .dproj file

        Triple validation ensures project source directories will not be mistakenly skipped as third-party libraries
        because they accidentally appear in IDE global library paths.

        Returns:
            Set of absolute paths to skip (normalized)
        """
        shared = self._get_shared_thirdparty_paths()
        if not shared:
            return set()

        # Collect third-party library paths inside project directory from .dproj
        dproj_inside = set()
        for p in self.get_thirdparty_paths_from_dproj():
            try:
                pp = Path(p).resolve()
                pp.relative_to(self.project_dir.resolve())
                dproj_inside.add(str(pp))
            except ValueError:
                pass  # Not inside project directory, do not participate in exclusion judgment

        if not dproj_inside:
            return set()

        # Intersection: appear in both shared KB and .dproj third-party library paths
        verified = set()
        for p in shared:
            pp_str = str(Path(p).resolve())
            if pp_str in dproj_inside:
                verified.add(pp_str)

        if verified:
            logger.info(f"Project source scan will skip {len(verified)} verified third-party library directories")
        return verified


    def _should_skip_shared_path(self, file_path: Path, exclude_prefixes: Set[str]) -> bool:
        """Check if file is under a shared knowledge base path that should be skipped"""
        if not exclude_prefixes:
            return False
        file_str = str(file_path.resolve())
        for prefix_str in exclude_prefixes:
            if file_str == prefix_str or file_str.startswith(prefix_str + os.sep):
                return True
        return False

    def build_project_knowledge_base(self, rebuild: bool = False) -> bool:
        """
        Build project source knowledge base (ZVec version)

        Args:
            rebuild: Whether to force rebuild

        Returns:
            Whether build succeeded
        """
        _build_start = time.time()

        # Migrate old zvec_project/ subdirectory to root directory
        from .zvec_adapter import _migrate_old_zvec_data
        old_zvec = self.kb_dir / "zvec_project"
        if old_zvec.exists() and old_zvec != self.kb_dir:
            _migrate_old_zvec_data(old_zvec, self.kb_dir)

        current_hash = self._calculate_source_hash(self.project_dir)
        if not rebuild:
            cached_hash = None
            hash_file = self.kb_dir / "source_hash.txt"
            if hash_file.exists():
                cached_hash = hash_file.read_text(encoding='utf-8').strip()
            if cached_hash == current_hash and any(f.name.startswith("manifest") for f in self.kb_dir.iterdir()):
                logger.info("Project source knowledge base is up to date, skipping build")
                return True

        logger.info("Starting to build project source knowledge base (ZVec)")
        self._report_progress(5, "Scanning project source files...")
        self.kb_dir.mkdir(parents=True, exist_ok=True)

        # Collect project source files
        exclude_prefixes = self._get_verified_thirdparty_prefixes()
        skip_dir_names = SOURCE_SCAN_EXCLUDED_DIRS
        delphi_extensions = {'.pas', '.dpr', '.dpk', '.dfm', '.fmx', '.inc'}

        project_files: List[str] = []
        for root, dirs, files in os.walk(self.project_dir):
            dirs[:] = [d for d in dirs if d.lower() not in skip_dir_names]
            root_path = Path(root)
            if self._should_skip_shared_path(root_path, exclude_prefixes):
                dirs[:] = []
                continue
            for file in files:
                if Path(file).suffix.lower() in delphi_extensions:
                    project_files.append(str(root_path / file))

        self._report_progress(30, f"Collected {len(project_files)} files, starting chunking...")

        # Chunk all files
        chunks = chunk_file_list(project_files)
        if not chunks:
            logger.warning("Project source produced no chunks")
            return False
        logger.info(f"Chunking complete: {len(chunks)} chunks from {len(project_files)} files")
        self._report_progress(50, f"{len(chunks)} chunks, importing into ZVec...")

        # Build ZVec knowledge base (flattened to kb_dir root)
        kv_dir = str(self.kb_dir)
        import zvec
        from zvec import CollectionSchema, FieldSchema, DataType, FtsIndexParam, InvertIndexParam, Doc

        # Open or create collection: open if valid collection exists, otherwise remove directory and create_and_open
        kv_path = Path(kv_dir)
        has_valid = kv_path.exists() and any(
            f.name.startswith("manifest") for f in kv_path.iterdir()
        )
        if has_valid:
            col = zvec.open(kv_dir)
            if rebuild:
                # Rebuild: close collection first to release Windows handles, then delete directory.
                # If not closed, open handles will make rmtree fail silently.
                try:
                    col.close()
                except Exception:
                    pass
                import shutil as _shutil
                _shutil.rmtree(kv_dir, ignore_errors=True)
                has_valid = False
        if not has_valid:
            if kv_path.exists():
                import shutil as _shutil
                _shutil.rmtree(kv_dir, ignore_errors=True)
            # Simplified schema: entity_name merged into chunk_text
            schema = CollectionSchema("project_kb", fields=[
                FieldSchema("chunk_text", DataType.STRING),
                FieldSchema("chunk_type", DataType.STRING),
                FieldSchema("base_class", DataType.STRING),
                FieldSchema("file_path", DataType.STRING),
                FieldSchema("start_line", DataType.INT32),
                FieldSchema("end_line", DataType.INT32),
            ])
            col = zvec.create_and_open(path=kv_dir, schema=schema)

        # Insert data first
        BATCH = 500
        for offset in range(0, len(chunks), BATCH):
            batch = chunks[offset:offset + BATCH]
            docs = []
            for i, c in enumerate(batch):
                docs.append(Doc(
                    id=f"c{offset + i:07d}",
                    fields={
                        "chunk_text": (str(c['entity_name'])[:500] + "\n" + str(c['chunk_text'])[:99480]),
                        "chunk_type": str(c['chunk_type']),
                        "base_class": str(c['base_class'])[:200],
                        "file_path": str(c['file_path'])[:500],
                        "start_line": c['start_line'],
                        "end_line": c['end_line'],
                    },
                ))
            col.insert(docs)
            if (offset // BATCH) % 10 == 0:
                pct = 50 + int(offset / len(chunks) * 40)
                self._report_progress(pct, f"Importing {offset + BATCH}/{len(chunks)}")

        col.flush()

        # Then create indexes
        col.create_index("chunk_text", FtsIndexParam(tokenizer_name="jieba"))
        col.create_index("chunk_type", InvertIndexParam())
        col.create_index("base_class", InvertIndexParam())
        col.optimize()
        col.flush()

        # Save source_hash
        hash_file = self.kb_dir / "source_hash.txt"
        hash_file.write_text(current_hash, encoding='utf-8')

        # Save build metadata
        class_count = sum(1 for c in chunks if c.get('chunk_type') in ('class', 'record', 'interface'))
        try:
            metadata = {
                "files": len(project_files),
                "classes": class_count,
                "chunks": len(chunks),
            }
            (self.kb_dir / "metadata.json").write_text(
                json.dumps(metadata, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except Exception as e:
            logger.warning(f"Failed to save project KB metadata: {e}")

        # Set project_kb as ZVec adapter
        self.project_kb = ZVecKnowledgeBaseAdapter(str(self.kb_dir), source_dirs=[str(self.project_dir)])

        _duration = int(time.time() - _build_start)
        logger.info(f"Project knowledge base build complete! {len(chunks)} chunks, took {_duration}s")
        self._report_progress(100, f"Project KB: {len(chunks)} chunks, {_duration}s")
        return True

    def check_and_update_project_kb(self) -> bool:
        """
        Check if project source has changes (ZVec version uses source_hash.txt)

        Returns:
            True means knowledge base is up to date, False means changes detected
        """
        current_hash = self._calculate_source_hash(self.project_dir)
        cached_hash = None
        hash_file = self.kb_dir / "source_hash.txt"
        if hash_file.exists():
            cached_hash = hash_file.read_text(encoding='utf-8').strip()

        if current_hash != cached_hash:
            logger.info("Project source changes detected (search will use old knowledge base, please manually trigger rebuild)")
            return False
        return True

    def load_knowledge_bases(self) -> bool:
        """
        Load ZVec knowledge base

        Returns:
            Whether loading succeeded
        """
        try:
            # Migrate old zvec_project/ subdirectory to root directory
            from .zvec_adapter import _migrate_old_zvec_data
            old_zvec = self.kb_dir / "zvec_project"
            if old_zvec.exists() and old_zvec != self.kb_dir:
                _migrate_old_zvec_data(old_zvec, self.kb_dir)
            # Check flattened ZVec data
            if any(f.name.startswith("manifest") for f in self.kb_dir.iterdir()):
                self.project_kb = ZVecKnowledgeBaseAdapter(str(self.kb_dir), source_dirs=[str(self.project_dir)])
                self.thirdparty_kb = self.project_kb
                logger.info(f"ZVec knowledge base loaded successfully: {self.kb_dir}")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to load ZVec knowledge base: {e}")
            return False

    def search_class(self, class_name: str, search_in: str = "all") -> List[Dict]:
        """
        Search class

        Args:
            class_name: Class name
            search_in: Search scope ("project", "thirdparty", "all")

        Returns:
            Search results
        """
        results = []

        # Check and update project knowledge base
        self.check_and_update_project_kb()

        if search_in in ("project", "all") and self.project_kb:
            results.extend(self.project_kb.search_by_class_name(class_name))

        if search_in in ("thirdparty", "all") and self.thirdparty_kb:
            results.extend(self.thirdparty_kb.search_by_class_name(class_name))

        return results

    def search_function(self, function_name: str, search_in: str = "all") -> List[Dict]:
        """
        Search function

        Args:
            function_name: Function name
            search_in: Search scope ("project", "thirdparty", "all")

        Returns:
            Search results
        """
        results = []

        # Check and update project knowledge base
        self.check_and_update_project_kb()

        if search_in in ("project", "all") and self.project_kb:
            results.extend(self.project_kb.search_by_function_name(function_name))

        if search_in in ("thirdparty", "all") and self.thirdparty_kb:
            results.extend(self.thirdparty_kb.search_by_function_name(function_name))

        return results

    def semantic_search(self, query: str, top_k: int = 10, search_in: str = "all") -> Dict:
        """
        Semantic search

        Args:
            query: Search query
            top_k: Number of results to return
            search_in: Search scope ("project", "thirdparty", "all")

        Returns:
            Search results {"classes": [...], "functions": [...]}
        """
        # Check and update project knowledge base
        self.check_and_update_project_kb()

        result = {
            "classes": [],
            "functions": []
        }

        if search_in in ("project", "all") and self.project_kb:
            class_results = self.project_kb.semantic_search_classes(query, top_k)
            func_results = self.project_kb.semantic_search_functions(query, top_k)

            for class_name, score in class_results:
                exact = self.project_kb.search_by_class_name(class_name)
                if exact:
                    result["classes"].append({
                        "source": "project",
                        "score": score,
                        "data": exact[0]
                    })

            for func_name, score in func_results:
                exact = self.project_kb.search_by_function_name(func_name)
                if exact:
                    result["functions"].append({
                        "source": "project",
                        "score": score,
                        "data": exact[0]
                    })

        if search_in in ("thirdparty", "all") and self.thirdparty_kb:
            class_results = self.thirdparty_kb.semantic_search_classes(query, top_k)
            func_results = self.thirdparty_kb.semantic_search_functions(query, top_k)

            for class_name, score in class_results:
                exact = self.thirdparty_kb.search_by_class_name(class_name)
                if exact:
                    result["classes"].append({
                        "source": "thirdparty",
                        "score": score,
                        "data": exact[0]
                    })

            for func_name, score in func_results:
                exact = self.thirdparty_kb.search_by_function_name(func_name)
                if exact:
                    result["functions"].append({
                        "source": "thirdparty",
                        "score": score,
                        "data": exact[0]
                    })

        # Sort by similarity
        result["classes"].sort(key=lambda x: x["score"], reverse=True)
        result["functions"].sort(key=lambda x: x["score"], reverse=True)

        return result

    def get_statistics(self) -> Dict:
        """
        Get knowledge base statistics (ZVec version)

        Returns:
            Statistics
        """
        stats = {"project": None, "thirdparty": None}

        # Prefer reading actual statistics from metadata.json
        metadata_file = self.kb_dir / "metadata.json"
        if metadata_file.exists():
            try:
                meta = json.loads(metadata_file.read_text(encoding="utf-8"))
                total_size = sum(
                    os.path.getsize(os.path.join(dp, f))
                    for dp, _, fs in os.walk(self.kb_dir) for f in fs
                )
                stats["project"] = {
                    "files": meta.get("files", 0),
                    "classes": meta.get("classes", 0),
                    "chunks": meta.get("chunks", 0),
                    "database_size_mb": round(total_size / (1024 * 1024), 1),
                }
                return stats
            except Exception:
                pass

        # fallback: zvec internal file count (old/no metadata data)
        zvec_dir = self.kb_dir
        if not any(f.name.startswith("manifest") for f in zvec_dir.iterdir() if zvec_dir.exists()):
            return stats

        try:
            chunk_count = 0
            for root, dirs, files in os.walk(zvec_dir):
                for f in files:
                    if f.endswith('.sst') or f.endswith('.ipc') or f.endswith('.proxima'):
                        chunk_count += 1

            total_size = sum(
                os.path.getsize(os.path.join(dp, f))
                for dp, _, fs in os.walk(zvec_dir) for f in fs
            )
            stats["project"] = {
                "files": chunk_count,
                "classes": chunk_count // 2,
                "database_size_mb": round(total_size / (1024 * 1024), 1),
            }
        except Exception as e:
            logger.debug(f"ZVec statistics failed: {e}")
        return stats

    def _report_progress(self, percent: float, message: str) -> None:
        """Report progress (safely call progress_callback)"""
        if self.progress_callback:
            try:
                self.progress_callback(percent, message)
            except Exception as e:
                logger.warning("progress_callback execution failed: %s", e)

    def build_vectors(self, progress_callback=None) -> dict:
        """ZVec version: indexes are created during insertion, no operation needed here"""
        return {"project": 0, "thirdparty": 0}

    def close(self):
        """Close knowledge base connection"""
        if self.project_kb:
            try:
                self.project_kb.close()
            except Exception:
                pass
            self.project_kb = None
        self.thirdparty_kb = None

