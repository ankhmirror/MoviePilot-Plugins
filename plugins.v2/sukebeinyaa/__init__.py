from typing import Any, Dict, List, Tuple, Optional

from app.plugins import _PluginBase

try:
    from app.core.sites import SitesHelper
except Exception:
    try:
        from app.core.indexer import SitesHelper
    except Exception:
        SitesHelper = None


class SukebeiNyaa(_PluginBase):
    plugin_name = "SukebeiNyaa"
    plugin_desc = "扩展索引站点 sukebei.nyaa.si"
    plugin_order = 99
    plugin_version = "1.0.0"
    plugin_author = "黄垚淮"
    plugin_icon = "https://raw.githubusercontent.com/jxxghp/MoviePilot-Plugins/main/icons/nyaa.png"

    _enabled: bool = False
    _proxy: bool = True

    def init_plugin(self, config: dict = None):
        if config:
            self._enabled = bool(config.get("enabled", False))
            self._proxy = bool(config.get("proxy", True))
        if self._enabled and SitesHelper:
            indexer: Dict[str, Any] = {
                "id": "sukebeinyaa",
                "name": "Sukebei Nyaa",
                "domain": "https://sukebei.nyaa.si/",
                "encoding": "UTF-8",
                "public": True,
                "proxy": self._proxy,
                "result_num": 100,
                "timeout": 30,
                "search": {
                    "paths": [
                        {
                            "path": "?f=0&c=0_0&q={keyword}",
                            "method": "get",
                        }
                    ]
                },
                "browse": {
                    "path": "?p={page}",
                    "start": 1,
                },
                "torrents": {
                    "list": {"selector": "table.torrent-list > tbody > tr"},
                    "fields": {
                        "id": {
                            "selector": "a[href*=\"/view/\"]",
                            "attribute": "href",
                            "filters": [
                                {"name": "re_search", "args": ["\\d+", 0]}
                            ],
                        },
                        "title": {"selector": "td:nth-child(2) > a"},
                        "details": {
                            "selector": "td:nth-child(2) > a",
                            "attribute": "href",
                        },
                        "download": {
                            "selector": "td:nth-child(3) > a[href*=\"/download/\"]",
                            "attribute": "href",
                        },
                        "date_added": {"selector": "td:nth-child(5)"},
                        "size": {"selector": "td:nth-child(4)"},
                        "seeders": {"selector": "td:nth-child(6)"},
                        "leechers": {"selector": "td:nth-child(7)"},
                        "grabs": {"selector": "td:nth-child(8)"},
                        "downloadvolumefactor": {"case": {"*": 0}},
                        "uploadvolumefactor": {"case": {"*": 1}},
                    },
                },
            }
            try:
                SitesHelper().add_indexer("https://sukebei.nyaa.si/", indexer)
            except Exception:
                pass

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
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 8},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {"model": "proxy", "label": "索引请求使用代理"},
                                    }
                                ],
                            },
                        ],
                    }
                ],
            }
        ], {"enabled": False, "proxy": True}

    def get_page(self) -> List[dict]:
        return []

    def get_module(self) -> Dict[str, Any]:
        return {}

    def stop_service(self):
        pass