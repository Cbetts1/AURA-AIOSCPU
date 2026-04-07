"""
AURA-AIOSCPU Shell Plugin Loader
==================================
Discovers and loads shell command plugins from shell/plugins/.

Plugin contract
---------------
Each plugin module must expose:
  PLUGIN_NAME    : str              — unique name (e.g. "system")
  COMMANDS       : dict[str, fn]    — command name → handler function
  HELP           : dict[str, str]   — command name → help text (optional)

Handler signature:
  def handle(shell, args: list[str]) -> str | None

The handler receives the Shell instance and the split args list.
It returns a string to print, or None for no output.

Plugin discovery
----------------
  1. Scans shell/plugins/*.py (ignoring __init__.py and _*.py).
  2. Imports each module.
  3. Validates the PLUGIN_NAME and COMMANDS attributes.
  4. Registers commands with the shell's command dispatch table.

Errors
------
  Import errors are logged as warnings — a bad plugin never crashes the shell.
"""

import importlib
import importlib.util
import logging
import os

logger = logging.getLogger(__name__)

_PLUGINS_DIR = os.path.join(os.path.dirname(__file__), "plugins")


class PluginLoader:
    """
    Loads and manages shell command plugins.

    Usage::

        loader = PluginLoader()
        loader.load_all()
        commands = loader.all_commands()   # merged command → handler map
        help_map = loader.all_help()       # command → help text
    """

    def __init__(self, plugins_dir: str | None = None):
        self._dir = plugins_dir or _PLUGINS_DIR
        self._plugins: dict[str, object] = {}          # name → module
        self._commands: dict[str, callable] = {}       # cmd → handler
        self._help: dict[str, str] = {}                # cmd → help text

    # ------------------------------------------------------------------
    # Load
    # ------------------------------------------------------------------

    def load_all(self) -> list[str]:
        """
        Scan the plugins directory and load all valid plugin modules.

        Returns a list of successfully loaded plugin names.
        """
        loaded = []
        if not os.path.isdir(self._dir):
            logger.debug("PluginLoader: plugins dir not found: %s", self._dir)
            return loaded

        for fname in sorted(os.listdir(self._dir)):
            if not fname.endswith(".py"):
                continue
            if fname.startswith(("__", "_")):
                continue
            module_name = fname[:-3]
            try:
                module = self._import_plugin(module_name)
                if module and self._register_plugin(module):
                    loaded.append(getattr(module, "PLUGIN_NAME", module_name))
            except Exception as exc:
                logger.warning("PluginLoader: failed to load %r: %s",
                               module_name, exc)

        logger.info("PluginLoader: loaded %d plugin(s): %s",
                    len(loaded), loaded)
        return loaded

    def load_plugin(self, name: str) -> bool:
        """Load a single plugin by module name. Returns True on success."""
        try:
            module = self._import_plugin(name)
            return bool(module and self._register_plugin(module))
        except Exception as exc:
            logger.warning("PluginLoader: failed to load %r: %s", name, exc)
            return False

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def all_commands(self) -> dict[str, callable]:
        """Return the merged command → handler map from all loaded plugins."""
        return dict(self._commands)

    def all_help(self) -> dict[str, str]:
        """Return the merged command → help text map from all loaded plugins."""
        return dict(self._help)

    def loaded_plugins(self) -> list[str]:
        return list(self._plugins.keys())

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _import_plugin(self, module_name: str):
        """Import a plugin module from the plugins directory."""
        spec_path = os.path.join(self._dir, f"{module_name}.py")
        if not os.path.isfile(spec_path):
            return None
        spec   = importlib.util.spec_from_file_location(
            f"shell.plugins.{module_name}", spec_path
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def _register_plugin(self, module) -> bool:
        """Validate and register a loaded plugin module."""
        name = getattr(module, "PLUGIN_NAME", None)
        cmds = getattr(module, "COMMANDS", None)
        if not name or not isinstance(cmds, dict):
            logger.warning(
                "PluginLoader: module %r missing PLUGIN_NAME or COMMANDS",
                getattr(module, "__name__", "?"),
            )
            return False

        self._plugins[name] = module
        for cmd, fn in cmds.items():
            if callable(fn):
                self._commands[cmd] = fn
        help_map = getattr(module, "HELP", {})
        for cmd, text in help_map.items():
            self._help[cmd] = text

        logger.debug("PluginLoader: registered plugin %r (%d commands)",
                     name, len(cmds))
        return True
