"""
Third-party library knowledge base service

Copyright (C) Jilin Zuoyou Software Development Co., Ltd.
Copyright (C) Equilibrium Software Development Co., Ltd, Jilin
Update & Mod By Crystalxp (Dark Night Killer QQ:281309196)

Provides knowledge base functionality for Delphi third-party libraries:
1. Read Library paths for Delphi version from registry
2. Parse Browsing Path and Search Path
3. Expand environment variables and deduplicate
4. Exclude Delphi built-in paths
5. Build third-party library knowledge base
"""

import os
import re
import json
import time
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Set, Callable
from datetime import datetime

try:
    from ...constants import REG_KEY_EMBARCADERO_BDS, REG_KEY_EMBARCADERO_STUDIO
    from .zvec_adapter import ZVecKnowledgeBaseAdapter
    from ...utils.logger import get_logger
    from ...utils.delphi_env import expand_delphi_path_macros, get_delphi_version, get_catalog_repository_paths
    logger = get_logger(__name__)
except ImportError:
    # Support direct test running
    from src.constants import REG_KEY_EMBARCADERO_BDS, REG_KEY_EMBARCADERO_STUDIO
    from zvec_adapter import ZVecKnowledgeBaseAdapter
    import logging
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
        logger.addHandler(handler)

    # Test mode fallback implementation
    def expand_delphi_path_macros(path: str, version: Optional[str] = None) -> str:
        return os.path.expandvars(path)

    def get_delphi_version() -> Optional[str]:
        return None

    def get_catalog_repository_paths(version: Optional[str] = None) -> list:
        return []


class ThirdPartyKnowledgeBase:
    """Third-party library knowledge base manager"""

    def __init__(self, kb_dir: Optional[str] = None, progress_callback: Optional[Callable] = None) -> None:
        """
        Initialize third-party library knowledge base

        Args:
            kb_dir: Knowledge base directory path; if None, use default path
            progress_callback: Progress callback function
        """
        self.kb_dir: Path
        if kb_dir is None:
            # Default path: data/thirdparty-knowledge-base under MCP server directory
            server_root = Path(__file__).parent.parent.parent.parent
            kb_dir = server_root / "data" / "thirdparty-knowledge-base"
        else:
            kb_dir = Path(kb_dir)

        self.kb_dir = kb_dir
        self.kb_instance = None
        self.delphi_versions = []
        self.environment_variables = {}  # Environment variable cache
        self.progress_callback = progress_callback

        # Create necessary directories
        self.kb_dir.mkdir(parents=True, exist_ok=True)

        # Metadata file
        self.metadata_file = self.kb_dir / "thirdparty_metadata.json"
        self.paths_file = self.kb_dir / "thirdparty_paths.json"

        # Load metadata
        self.metadata = self._load_metadata()

        # Detect Delphi versions
        self.detect_delphi_versions()

        logger.info("Third-party library knowledge base initialization complete")

    def _load_metadata(self) -> Dict:
        """Load metadata"""
        if self.metadata_file.exists():
            try:
                with open(self.metadata_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load metadata: {e}")

        return {
            "created_at": datetime.now().isoformat(),
            "last_updated": datetime.now().isoformat(),
            "version": "1.0",
            "total_paths": 0,
            "scanned_paths": []
        }

    def _save_metadata(self):
        """Save metadata"""
        self.metadata["last_updated"] = datetime.now().isoformat()
        with open(self.metadata_file, 'w', encoding='utf-8') as f:
            json.dump(self.metadata, f, ensure_ascii=False, indent=2)

    def detect_delphi_versions(self) -> List[Dict]:
        """
        Detect installed Delphi versions

        Returns:
            List of Delphi versions
        """
        import winreg

        versions = []

        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY_EMBARCADERO_BDS)

            i = 0
            while True:
                try:
                    version_key = winreg.EnumKey(key, i)
                    i += 1

                    version_path = winreg.OpenKey(key, version_key)
                    try:
                        root_dir = winreg.QueryValueEx(version_path, "RootDir")[0]
                    except OSError:
                        continue
                    finally:
                        winreg.CloseKey(version_path)

                    version_name = self._get_delphi_name_by_version_key(version_key)

                    versions.append({
                        "version": version_key,
                        "name": version_name,
                        "root_dir": root_dir
                    })

                except WindowsError:
                    break

            winreg.CloseKey(key)

        except Exception as e:
            logger.warning(f"Failed to detect Delphi versions: {e}")

        self.delphi_versions = versions
        return versions

    def get_latest_version(self) -> Optional[Dict]:
        """Get latest installed Delphi version"""
        if not self.delphi_versions:
            return None
        # Sort by version number, return latest version
        sorted_versions = sorted(
            self.delphi_versions,
            key=lambda x: tuple(int(p) for p in x["version"].split('.')),
            reverse=True
        )
        return sorted_versions[0]

    def _get_delphi_name_by_version_key(self, version_key: str) -> str:
        """Get Delphi version name from registry version key (e.g. "22.0")

        Note the difference from config_manager._get_delphi_version_name:
        the latter resolves version name by installation path, while this method resolves by registry key name.
        """
        from src.utils.delphi_versions import get_version_name
        return get_version_name(version_key)

    def _load_environment_variables(self, version: str) -> Dict[str, str]:
        """
        Load environment variables for specified Delphi version

        Args:
            version: Delphi version number (e.g. "37.0")

        Returns:
            Environment variable dictionary
        """
        import winreg

        env_vars = {}

        try:
            key_path = f"{REG_KEY_EMBARCADERO_BDS}\\{version}\\Environment Variables"
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path)

            i = 0
            while True:
                try:
                    name, value, _ = winreg.EnumValue(key, i)
                    env_vars[name] = value
                    i += 1
                except WindowsError:
                    break

            winreg.CloseKey(key)

        except Exception as e:
            logger.warning(f"Failed to load environment variables (version {version}): {e}")

        return env_vars

    def _expand_path_variables(self, path: str, env_vars: Dict[str, str]) -> str:
        """
        Expand environment variables in path

        Args:
            path: Original path (may contain $(VAR) format)
            env_vars: Environment variable dictionary

        Returns:
            Expanded path
        """
        # Match variables in $(VAR) format
        pattern = r'\$\(([^)]+)\)'

        def replace_var(match):
            var_name = match.group(1)
            if var_name in env_vars:
                return env_vars[var_name]
            # Keep undefined variables
            return match.group(0)

        return re.sub(pattern, replace_var, path)

    def _is_delphi_system_path(self, path: str, version_key: Optional[str] = None) -> bool:
        """
        Check if path is a Delphi system path

        Args:
            path: Path string
            version_key: Delphi version number

        Returns:
            Whether it is a system path
        """
        path_lower = path.lower()

        # Check if contains Delphi system path variables
        system_vars = ['$(bdsccommondir)', '$(bdslib)', '$(bds)', '$(bdsbin)', '$(bdsuserdir)']
        for var in system_vars:
            if var in path_lower:
                return True

        # Check if under Delphi installation directory
        for version in self.delphi_versions:
            root_dir = version.get("root_dir", "")
            if root_dir and path_lower.startswith(root_dir.lower()):
                return True

        # Check if it is a Delphi system directory under public documents
        user_docs = os.path.expanduser("~\\Documents").lower()
        delphi_common_dirs = ['imports', 'bpl', 'dcp', 'bpl\\win32', 'bpl\\win64', 'dcp\\win32', 'dcp\\win64']
        if path_lower.startswith(user_docs + '\\embarcadero\\studio\\'):
            relative = path_lower[len(user_docs + '\\embarcadero\\studio\\'):]
            for sys_dir in delphi_common_dirs:
                if relative.startswith(sys_dir):
                    return True

        return False

    def get_library_paths(self, version: Optional[str] = None) -> List[str]:
        """
        Get Library paths for specified Delphi version

        Args:
            version: Delphi version number; if None, use latest version

        Returns:
            List of third-party library paths
        """
        import winreg

        # Long-running service scenario: service starts before compiler installation; detect_delphi_versions at __init__
        # caches empty result. Directly returning [] would make delphi_kb build kb_type=thirdparty
        # succeed without doing work. Here, when cache is empty, re-detect registry to pick up newly installed compiler.
        if not self.delphi_versions:
            logger.info("Delphi version cache is empty, re-detecting registry...")
            self.detect_delphi_versions()

        # Select Delphi version
        if not self.delphi_versions:
            logger.error("No Delphi version detected")
            return []

        if version is None:
            selected_version = self.get_latest_version()
        else:
            selected_version = None
            for v in self.delphi_versions:
                if v["version"] == version or v["name"] == version:
                    selected_version = v
                    break

        if not selected_version:
            logger.error(f"Delphi version not found: {version}")
            return []

        version_key = selected_version["version"]
        logger.info(f"Using Delphi version: {selected_version['name']} ({version_key})")

        # Load environment variables
        env_vars = self._load_environment_variables(version_key)
        self.environment_variables = env_vars

        all_paths = []

        # Read BDS Library paths
        try:
            library_key_path = f"{REG_KEY_EMBARCADERO_BDS}\\{version_key}\\Library"
            library_key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, library_key_path)
            all_paths.extend(self._read_library_paths(library_key, version_key))
            winreg.CloseKey(library_key)
        except Exception as e:
            logger.debug(f"Failed to read BDS Library paths: {e}")

        # Read Studio Library paths (common library paths)
        try:
            studio_key_path = f"{REG_KEY_EMBARCADERO_STUDIO}\\{version_key}\\Library"
            studio_key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, studio_key_path)
            all_paths.extend(self._read_library_paths(studio_key, version_key))
            winreg.CloseKey(studio_key)
        except Exception as e:
            logger.debug(f"Failed to read Studio Library paths: {e}")

        # Deduplicate and preserve order
        seen = set()
        unique_paths = []
        for path in all_paths:
            if path not in seen:
                seen.add(path)
                unique_paths.append(path)

        logger.info(f"Read {len(unique_paths)} unique paths from registry")

        # Expand environment variables and filter
        thirdparty_paths = []
        for path in unique_paths:
            # Expand environment variables first, then use expanded path to determine if system path
            try:
                expanded_path = expand_delphi_path_macros(path, version=version_key)
            except Exception:
                # Fall back to original expansion method
                expanded_path = self._expand_path_variables(path, env_vars)

            # Skip Delphi system paths (judge after expansion to avoid $(BDS) macro mistakenly killing all paths)
            if self._is_delphi_system_path(expanded_path):
                logger.debug(f"Skipping Delphi system path: {expanded_path}")
                continue

            # Check if path exists
            path_obj = Path(expanded_path)
            if path_obj.exists():
                thirdparty_paths.append(str(path_obj.resolve()))
            else:
                # Try to expand GetIt CatalogRepository path
                if 'CatalogRepository' in expanded_path:
                    logger.debug(f"GetIt path does not exist: {expanded_path}")

        # Final deduplication
        seen = set()
        final_paths = []
        for path in thirdparty_paths:
            if path not in seen:
                seen.add(path)
                final_paths.append(path)

        logger.info(f"After filtering, got {len(final_paths)} third-party library paths")

        # Additionally add component source paths from GetIt CatalogRepository
        try:
            getit_paths = get_catalog_repository_paths(version_key)
            for getit_path in getit_paths:
                if getit_path not in final_paths:
                    final_paths.append(getit_path)
                    logger.debug(f"Adding GetIt component path: {getit_path}")
        except Exception as e:
            logger.warning(f"Failed to get GetIt paths: {e}")

        logger.info(f"Finally got {len(final_paths)} third-party library paths")

        # Save path list
        self._save_paths(final_paths, selected_version)

        return final_paths

    def _read_library_paths(self, library_key, version_key: str) -> List[str]:
        """Read paths from registry Library key"""
        import winreg
        paths = []
        
        # Iterate over all platforms (Win32, Win64, etc.)
        i = 0
        while True:
            try:
                platform_name = winreg.EnumKey(library_key, i)
                i += 1

                platform_key = winreg.OpenKey(library_key, platform_name)

                try:
                    # Read Browsing Path
                    try:
                        browsing_path = winreg.QueryValueEx(platform_key, "Browsing Path")[0]
                        if browsing_path:
                            p_list = [p.strip() for p in browsing_path.split(';') if p.strip()]
                            paths.extend(p_list)
                            logger.debug(f"Platform {platform_name} Browsing Path: {len(p_list)} paths")
                    except OSError:
                        pass

                    # Read Search Path
                    try:
                        search_path = winreg.QueryValueEx(platform_key, "Search Path")[0]
                        if search_path:
                            p_list = [p.strip() for p in search_path.split(';') if p.strip()]
                            paths.extend(p_list)
                            logger.debug(f"Platform {platform_name} Search Path: {len(p_list)} paths")
                    except OSError:
                        pass

                finally:
                    winreg.CloseKey(platform_key)

            except WindowsError:
                break
        
        return paths

    def _report_progress(self, percent: float, message: str) -> None:
        """Report progress (safely call progress_callback)"""
        if self.progress_callback:
            try:
                self.progress_callback(percent, message)
            except Exception as e:
                logger.debug("Ignoring non-fatal exception: %s", str(e))

    def _save_paths(self, paths: List[str], version_info: Dict):
        """Save path list"""
        data = {
            "version": version_info,
            "paths": paths,
            "count": len(paths),
            "saved_at": datetime.now().isoformat()
        }

        with open(self.paths_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info(f"Path list saved to: {self.paths_file}")

    def build_thirdparty_knowledge_base(self, version: Optional[str] = None, rebuild: bool = False) -> bool:
        """Build third-party library knowledge base (ZVec)"""
        import time, shutil
        from pathlib import Path
        _bt = time.time()
        logger.info("Building thirdparty KB (ZVec)")

        dirs = self.get_library_paths(version)
        if not dirs:
            logger.warning("No thirdparty dirs"); return True

        self._report_progress(5, "Scanning dirs...")
        files = self._collect_thirdparty_files(dirs)
        if not files:
            logger.warning("No thirdparty files to index"); return True
        logger.info("Collected " + str(len(files)) + " files")

        from .delphi_chunker import chunk_file_list
        chunks = chunk_file_list(files)
        if not chunks:
            logger.warning("No chunks"); return False
        logger.info("Chunked: " + str(len(chunks)))

        # Migrate old zvec_thirdparty/ subdirectory to root directory
        from .zvec_adapter import _migrate_old_zvec_data
        old_zvec = self.kb_dir / "zvec_thirdparty"
        if old_zvec.exists() and old_zvec != self.kb_dir:
            _migrate_old_zvec_data(old_zvec, self.kb_dir)

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
                # If not closed, open handles (e.g. RocksDB LOCK) will make rmtree fail silently.
                try:
                    col.close()
                except Exception:
                    pass
                import shutil as _shutil
                _shutil.rmtree(kv_dir, ignore_errors=True)
                has_valid = False  # fall through to create_and_open
        if not has_valid:
            if kv_path.exists():
                import shutil as _shutil
                _shutil.rmtree(kv_dir, ignore_errors=True)
            # Simplified schema: entity_name merged into chunk_text
            schema = CollectionSchema("thirdparty_kb", fields=[
                FieldSchema("chunk_text", DataType.STRING),
                FieldSchema("chunk_type", DataType.STRING),
                FieldSchema("base_class", DataType.STRING),
                FieldSchema("file_path", DataType.STRING),
                FieldSchema("start_line", DataType.INT32),
                FieldSchema("end_line", DataType.INT32),
            ])
            col = zvec.create_and_open(path=kv_dir, schema=schema)

        # Insert data first
        for offset in range(0, len(chunks), 500):
            batch = chunks[offset:offset+500]
            docs = []
            for i, c in enumerate(batch):
                docs.append(Doc(id="c%07d" % (offset+i), fields={
                    "chunk_text": (str(c['entity_name'])[:500] + "\n" + str(c['chunk_text'])[:99480]),
                    "chunk_type": str(c['chunk_type']),
                    "base_class": str(c['base_class'])[:200],
                    "file_path": str(c['file_path'])[:500],
                    "start_line": c['start_line'],
                    "end_line": c['end_line'],
                }))
            col.insert(docs)
        col.flush()

        # Then create indexes (repeating create_index on existing collection is safe, zvec will not error)
        col.create_index("chunk_text", FtsIndexParam(tokenizer_name="jieba"))
        col.create_index("chunk_type", InvertIndexParam())
        col.create_index("base_class", InvertIndexParam())
        col.optimize()
        col.flush()

        # Save build metadata
        class_count = sum(1 for c in chunks if c.get('chunk_type') in ('class', 'record', 'interface'))
        try:
            metadata = {
                "files": len(files),
                "classes": class_count,
                "chunks": len(chunks),
            }
            (self.kb_dir / "metadata.json").write_text(
                json.dumps(metadata, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except Exception as e:
            logger.warning(f"Failed to save third-party KB metadata: {e}")

        self.kb_instance = ZVecKnowledgeBaseAdapter(str(self.kb_dir), source_dirs=dirs)
        logger.info("3rd party KB done: %d chunks in %ds" % (len(chunks), int(time.time()-_bt)))
        return True

    def _collect_thirdparty_files(self, dirs: list) -> list:
        """Collect .pas files under third-party library directories"""
        files = []
        for d in dirs:
            p = Path(d)
            if p.exists():
                for f in p.rglob("*.pas"):
                    if f.is_file():
                        files.append(str(f))
        return files

    def _scan_help_documents(self, base_path: str) -> List[Dict]:
        """
        Scan help documents (HTML/CHM)
        
        Args:
            base_path: Base path
            
        Returns:
            List of help documents
        """
        help_docs = []
        
        # Scan HTML files - more lenient scanning
        for root, dirs, files in os.walk(base_path):
            # Skip hidden directories and common irrelevant directories
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in [
                'node_modules', 'vendor', 'lib', 'dist', 'bin', 'obj', '__pycache__'
            ]]
            
            for file in files:
                if file.lower().endswith(('.html', '.htm')):
                    # Skip index files
                    if file.lower() in ['index.html', 'index.htm', 'toc.html', 'contents.html']:
                        continue
                    
                    file_path = os.path.join(root, file)
                    try:
                        # Only process smaller files (help documents are usually not too large)
                        if os.path.getsize(file_path) > 5 * 1024 * 1024:  # 5MB
                            continue
                            
                        doc = self._parse_html_help(file_path, base_path)
                        if doc and (doc.get('classes') or doc.get('functions')):
                            help_docs.append(doc)
                    except Exception as e:
                        logger.debug(f"Failed to parse help document: {file_path}, {e}")
        
        return help_docs

    def _parse_html_help(self, file_path: str, base_path: str) -> Optional[Dict]:
        """
        Parse HTML help document
        
        Args:
            file_path: File path
            base_path: Base path

        Returns:
            Parsed document
        """
        try:
            from bs4 import BeautifulSoup
            
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            soup = BeautifulSoup(content, 'html.parser')
            
            # Extract title
            title = ''
            h1 = soup.find('h1')
            if h1:
                title = h1.get_text().strip()
            if not title:
                title_elem = soup.find('title')
                if title_elem:
                    title = title_elem.get_text().strip()
            if not title:
                title = os.path.basename(file_path)
            
            # Extract class names (from title or content)
            classes = []
            functions = []
            properties = []
            events = []
            
            # Common patterns: TClassName, TInterfaceName
            import re
            class_pattern = re.compile(r'\b(T[A-Z][A-Za-z0-9_]+)\b')
            
            # Extract from title
            if title:
                matches = class_pattern.findall(title)
                for match in matches:
                    if match not in [c['name'] for c in classes]:
                        classes.append({
                            'name': match,
                            'base_class': '',
                            'description': title
                        })
            
            # Extract from content
            text = soup.get_text()
            matches = class_pattern.findall(text)
            for match in matches:
                if match not in [c['name'] for c in classes]:
                    classes.append({
                        'name': match,
                        'base_class': '',
                        'description': ''
                    })
            
            # Extract functions/methods
            func_pattern = re.compile(r'\b([A-Z][a-zA-Z0-9_]+)\s*\([^)]*\)\s*(?:of\s+object)?;?', re.IGNORECASE)
            func_matches = func_pattern.findall(text)
            for func_name in func_matches[:20]:  # Limit quantity
                if func_name not in [f['name'] for f in functions]:
                    functions.append({
                        'name': func_name,
                        'description': ''
                    })
            
            # Extract properties
            prop_pattern = re.compile(r'\bproperty\s+([A-Za-z_][A-Za-z0-9_]*)', re.IGNORECASE)
            prop_matches = prop_pattern.findall(text)
            for prop_name in prop_matches[:20]:
                if prop_name not in [p['name'] for p in properties]:
                    properties.append({
                        'name': prop_name,
                        'description': ''
                    })
            
            # Extract events
            event_pattern = re.compile(r'\bOn([A-Z][a-zA-Z0-9_]+)', re.IGNORECASE)
            event_matches = event_pattern.findall(text)
            for event_name in event_matches[:20]:
                full_name = 'On' + event_name
                if full_name not in [e['name'] for e in events]:
                    events.append({
                        'name': full_name,
                        'description': ''
                    })
            
            stat = os.stat(file_path)
            
            return {
                'full_path': file_path,
                'path': os.path.relpath(file_path, base_path),
                'extension': '.html',
                'size': stat.st_size,
                'line_count': content.count('\n'),
                'last_modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                'title': title,
                'classes': classes,
                'functions': functions,
                'properties': properties,
                'events': events
            }
            
        except Exception as e:
            logger.debug(f"Failed to parse HTML: {file_path}, {e}")
            return None

    def load_knowledge_base(self) -> bool:
        try:
            # Migrate old zvec_thirdparty/ subdirectory to root directory
            from .zvec_adapter import _migrate_old_zvec_data
            old_zvec = self.kb_dir / "zvec_thirdparty"
            if old_zvec.exists() and old_zvec != self.kb_dir:
                _migrate_old_zvec_data(old_zvec, self.kb_dir)
            # Check flattened ZVec data
            if any(f.name.startswith("manifest") for f in self.kb_dir.iterdir()):
                self.kb_instance = ZVecKnowledgeBaseAdapter(str(self.kb_dir))
                return True
            return False
        except Exception as e:
            logger.error("Load 3rd KB failed: %s" % e)
            return False

    def search_by_class_name(self, class_name: str) -> List[Dict]:
        if not self.kb_instance: return []
        return self.kb_instance.search_by_name(class_name)

    def search_by_function_name(self, function_name: str) -> List[Dict]:
        if not self.kb_instance: return []
        return self.kb_instance.search_by_name(function_name)

    def semantic_search_classes(self, query: str, top_k: int = 10) -> List:
        if not self.kb_instance: return []
        return self.kb_instance.semantic_search_classes(query, top_k)
    def semantic_search_functions(self, query: str, top_k: int = 10) -> List:
        if not self.kb_instance: return []
        return self.kb_instance.semantic_search_functions(query, top_k)
    def get_statistics(self) -> Dict:
        # Prefer reading actual statistics from metadata.json
        metadata_file = self.kb_dir / "metadata.json"
        if metadata_file.exists():
            try:
                meta = json.loads(metadata_file.read_text(encoding="utf-8"))
                sz = sum(os.path.getsize(os.path.join(dp, f)) for dp, _, fs in os.walk(self.kb_dir) for f in fs)
                return {
                    "files": meta.get("files", 0),
                    "classes": meta.get("classes", 0),
                    "database_size_mb": round(sz / (1024 * 1024), 1),
                }
            except Exception:
                pass
        # fallback: zvec internal file count (old data)
        if not any(f.name.startswith("manifest") for f in self.kb_dir.iterdir() if self.kb_dir.exists()):
            return {"files": 0, "classes": 0, "database_size_mb": 0}
        chunk_count = 0
        for root, dirs, files in os.walk(self.kb_dir):
            for f in files:
                if f.endswith('.sst') or f.endswith('.ipc') or f.endswith('.proxima'):
                    chunk_count += 1
        sz = sum(os.path.getsize(os.path.join(dp, f)) for dp, _, fs in os.walk(self.kb_dir) for f in fs)
        return {"files": chunk_count, "classes": chunk_count // 2, "database_size_mb": round(sz / (1024*1024), 1)}

    def close(self):
        """Close knowledge base connection"""
        if self.kb_instance:
            self.kb_instance.close()
            self.kb_instance = None
