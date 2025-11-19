from typing import Any, Dict, List, Tuple, Optional

from app.plugins import _PluginBase

try:
    from app.helper.sites import SitesHelper  # noqa
except Exception:
    SitesHelper = None


class SukebeiNyaa(_PluginBase):
    plugin_name = "SukebeiNyaa"
    plugin_desc = "扩展索引站点 sukebei.nyaa.si"
    plugin_order = 99
    plugin_version = "1.1.0"
    plugin_author = "踏马奔腾"
    plugin_icon = "https://raw.githubusercontent.com/jxxghp/MoviePilot-Plugins/main/icons/nyaa.png"

    _enabled: bool = False
    _proxy: bool = True
    _domain: str = "https://sukebei.nyaa.si/"

    def _build_indexer(self) -> Dict[str, Any]:
        return {
            "id": 1,
            "name": "Sukebei Nyaa",
            "domain": self._domain,
            "encoding": "UTF-8",
            "public": True,
            "proxy": self._proxy,
            "result_num": 100,
            "timeout": 30,
            "search": {
                "paths": [
                    {
                        "path": "?f=0&c=1_1&q={keyword}",
                        "method": "get",
                    }
                ]
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

    def init_plugin(self, config: dict = None):
        if config:
            self._enabled = bool(config.get("enabled", False))
            self._proxy = bool(config.get("proxy", True))
        if self._enabled and SitesHelper:
            try:
                SitesHelper().add_indexer(self._domain, self._build_indexer())
            except Exception:
                pass

    def get_state(self) -> bool:
        return self._enabled

    def get_api(self) -> List[Dict[str, Any]]:
        return [
            {
                "path": "/refresh_sukebei",
                "endpoint": self.refresh_site,
                "methods": ["GET"],
                "auth": "apikey",
                "summary": "刷新 Sukebei 站点配置",
                "description": "重新注册 sukebei.nyaa.si 索引站点",
            }
        ]

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

    def refresh_site(self, **kwargs) -> Dict[str, Any]:
        ok = False
        if SitesHelper:
            try:
                SitesHelper().add_indexer(self._domain, self._build_indexer())
                ok = True
            except Exception:
                ok = False
        return {"ok": ok}