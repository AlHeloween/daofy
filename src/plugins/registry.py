"""
Plugin registry

Dynamic discovery + registration + routing by file extension + handler dispatch.

Core mechanisms:
  1. discover(plugins_dir) scans src/plugins/*/plugin.py,
     importlib dynamically loads and instantiates CompilerPlugin subclasses.
  2. register_handlers(handlers, descriptions, schemas, owner) registers handlers + schemas,
     called by each plugin's handler module itself.
  3. collect_tools() returns all tool definitions (ToolDefinition), for use by list_tools().
  4. get_handler() routes to a handler by tool name, for use by call_tool().
"""

import importlib
import logging
from typing import Dict, List, Optional, Any, Callable
from pathlib import Path

from .base import CompilerPlugin, PluginInfo, ToolDefinition

logger = logging.getLogger(__name__)


class PluginRegistry:
    """Plugin registry — dynamic discovery + handler dispatch + schema collection"""

    def __init__(self):
        self._plugins: Dict[str, CompilerPlugin] = {}  # name -> plugin
        self._ext_map: Dict[str, str] = {}  # ext -> plugin_name
        self._tool_handlers: Dict[str, Callable] = {}  # tool_name -> handler
        self._tool_descriptions: Dict[str, str] = {}  # tool_name -> description
        self._tool_schemas: Dict[str, Dict[str, Any]] = {}  # tool_name -> inputSchema
        self._tool_owner: Dict[str, str] = {}  # tool_name -> plugin_name
        self._aliases: set = set()  # alias tool names (not exposed to MCP clients)

    # ── Plugin dynamic discovery ──

    def discover(self, plugins_dir: str | Path) -> None:
        """Scan plugins_dir/*/plugin.py and dynamically load CompilerPlugin subclasses.

        Directory structure convention:
          src/plugins/<name>/
            __init__.py
            plugin.py    # must contain a CompilerPlugin subclass
            handlers.py  # optional, handler functions

        Skip:
          - __pycache__, directories starting with _ or .
          - non-plugin directories such as base.py, registry.py
          - core/ directory (core tools are registered separately)
        """
        plugins_path = Path(plugins_dir)
        if not plugins_path.is_dir():
            logger.warning(f"Plugin directory does not exist: {plugins_path}")
            return

        for pkg_dir in sorted(plugins_path.iterdir()):
            if not pkg_dir.is_dir():
                continue
            name = pkg_dir.name
            # Skip special directories
            if name.startswith(("_", ".")) or name == "core":
                continue
            plugin_file = pkg_dir / "plugin.py"
            if not plugin_file.exists():
                continue

            try:
                module = importlib.import_module(f"src.plugins.{name}.plugin")
            except Exception as e:
                logger.error(f"Failed to import plugin module: src.plugins.{name}.plugin — {e}", exc_info=True)
                continue

            # Find CompilerPlugin subclasses
            found = False
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (isinstance(attr, type)
                        and issubclass(attr, CompilerPlugin)
                        and attr is not CompilerPlugin):
                    try:
                        plugin_instance = attr()
                        self.register(plugin_instance)
                        found = True
                        logger.info(f"Dynamically loaded plugin: {plugin_instance.info.display_name} "
                                    f"(tools: {plugin_instance.get_owned_tool_names()})")
                    except Exception as e:
                        logger.error(f"Failed to instantiate plugin {attr_name}: {e}", exc_info=True)

            if not found:
                logger.warning(f"No CompilerPlugin subclass found in plugin directory {name}/")

    # ── Plugin registration ──

    def register(self, plugin: CompilerPlugin) -> None:
        """Register a plugin + collect its ToolDefinitions (including handler + schema)

        If plugin.is_available() returns False, skip tool registration for this plugin
        and keep only plugin metadata (name, extension mapping) to avoid exposing unavailable tools.
        """
        info = plugin.info
        self._plugins[info.name] = plugin
        for ext in info.supported_extensions:
            self._ext_map[ext.lower()] = info.name

        if not plugin.is_available():
            logger.info(f"No development tools detected for plugin {info.display_name}; skipping tool registration")
            return

        # Collect tool ownership declared by the plugin
        for tool_name in plugin.get_owned_tool_names():
            self._tool_owner[tool_name] = info.name

        # Collect handler + schema + description from get_tools()
        for tool_def in plugin.get_tools():
            if tool_def.handler:
                self._tool_handlers[tool_def.name] = tool_def.handler
            if tool_def.description:
                self._tool_descriptions[tool_def.name] = tool_def.description
            if tool_def.input_schema:
                self._tool_schemas[tool_def.name] = tool_def.input_schema

    # ── Handler module registration (called by each plugin's handler module itself) ──

    def register_handlers(
        self,
        handlers: Dict[str, Callable],
        descriptions: Dict[str, str] | None = None,
        schemas: Dict[str, Dict[str, Any]] | None = None,
        owner: str | None = None,
        aliases: set | None = None,
    ) -> None:
        """Register tools exported by a handler module — register handler + description + schema at once.

        Called by each plugin's handlers.py module at import time:
            _plugin_registry.register_handlers(
                CORE_HANDLERS, CORE_TOOL_DESCRIPTIONS, CORE_TOOL_SCHEMAS)
        """
        for name, handler in handlers.items():
            self._tool_handlers[name] = handler
            if owner:
                self._tool_owner[name] = owner
        if descriptions:
            self._tool_descriptions.update(descriptions)
        if schemas:
            self._tool_schemas.update(schemas)
        if aliases:
            self._aliases.update(aliases)

    def get_handler(self, tool_name: str) -> Optional[Callable]:
        """Get handler by tool name"""
        return self._tool_handlers.get(tool_name)

    # ── Tool definition collection (for list_tools) ──

    def collect_tools(self) -> List[ToolDefinition]:
        """Collect all tool definitions (plugin + core) for server.py list_tools().

        Returned ToolDefinition includes name, description, inputSchema, handler.
        Alias tools (such as file_tool) are not included.
        """
        tools: List[ToolDefinition] = []
        for name in self._tool_handlers:
            if name in self._aliases:
                continue
            tools.append(ToolDefinition(
                name=name,
                description=self._tool_descriptions.get(name, f"Tool: {name}"),
                input_schema=self._tool_schemas.get(name, {"type": "object", "properties": {}}),
                handler=self._tool_handlers[name],
            ))
        return tools

    # ── Query methods ──

    def get_plugin(self, name: str) -> Optional[CompilerPlugin]:
        """Get plugin by name"""
        return self._plugins.get(name)

    def get_plugin_for_file(self, file_path: str) -> Optional[CompilerPlugin]:
        """Get plugin by file extension"""
        ext = Path(file_path).suffix.lower()
        name = self._ext_map.get(ext)
        if name:
            return self._plugins.get(name)
        return None

    def get_all_plugins(self) -> List[CompilerPlugin]:
        """Get all registered plugins"""
        return list(self._plugins.values())

    def get_all_extensions(self) -> Dict[str, str]:
        """Get extension -> plugin name mapping"""
        return dict(self._ext_map)

    def get_tool_owner(self, tool_name: str) -> Optional[str]:
        """Get the plugin name that owns a tool"""
        return self._tool_owner.get(tool_name)

    def get_plugin_tools(self, plugin_name: str) -> List[str]:
        """Get the list of tool names owned by the specified plugin"""
        return [name for name, owner in self._tool_owner.items()
                if owner == plugin_name]

    def get_core_tools(self) -> List[str]:
        """Get the list of core (non-plugin) tool names"""
        return [name for name in self._tool_handlers
                if name not in self._tool_owner]

    def dispatch(self, tool_name: str, arguments: dict) -> Any:
        """Dispatch a tool call to the corresponding handler"""
        handler = self._tool_handlers.get(tool_name)
        if handler:
            return handler(arguments)
        return None

