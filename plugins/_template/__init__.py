from typing import Any, Dict, List, Tuple

from app.plugins import _PluginBase


class PluginTemplate(_PluginBase):
    plugin_name = "PluginTemplate"
    plugin_desc = "插件模板"
    plugin_order = 100
    plugin_version = "1.0.0"
    plugin_author = "User"

    _enabled: bool = False

    def init_plugin(self, config: dict = None):
        if config:
            self._enabled = bool(config.get("enabled", False))

    def get_state(self) -> bool:
        return self._enabled

    def get_api(self) -> List[Dict[str, Any]]:
        return []

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        return [
            {
                "component": "VForm",
                "content": [
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {"model": "enabled", "label": "启用插件"},
                                    }
                                ],
                            },
                        ],
                    }
                ],
            }
        ], {"enabled": False}

    def get_page(self) -> List[dict]:
        return []

    def get_module(self) -> Dict[str, Any]:
        return {}

    def stop_service(self):
        pass