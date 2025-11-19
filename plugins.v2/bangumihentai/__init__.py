from typing import Any, Dict, List, Tuple, Optional

from app.core.config import settings
from app.plugins import _PluginBase
from app.utils.http import RequestUtils
from app.core.context import MediaInfo


class BangumiHentai(_PluginBase):
    plugin_name = "BangumiHentai"
    plugin_desc = "在探索的 Bangumi 类别增加 里番"
    plugin_order = 98
    plugin_version = "1.0.0"
    plugin_author = "踏马奔腾"
    plugin_icon = "https://raw.githubusercontent.com/jxxghp/MoviePilot-Plugins/main/icons/bangumi.png"

    _enabled: bool = False
    _authorization: str = ""

    def init_plugin(self, config: dict = None):
        if config:
            self._enabled = bool(config.get("enabled", False))
            self._authorization = str(config.get("authorization", "") or "")

    def get_state(self) -> bool:
        return self._enabled

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
                                        "component": "VTextField",
                                        "props": {
                                            "model": "authorization",
                                            "label": "Bangumi Authorization",
                                            "clearable": True,
                                        },
                                    }
                                ],
                            },
                        ],
                    }
                ],
            }
        ], {"enabled": False, "authorization": ""}

    def get_api(self) -> List[Dict[str, Any]]:
        return [
            {
                "path": "/bangumi_hentai",
                "endpoint": self.bangumi_hentai,
                "methods": ["GET"],
                "summary": "Bangumi 里番",
                "description": "返回 Bangumi 中含有里番标签的条目",
            }
        ]

    def bangumi_hentai(self, page: int = 1, **kwargs) -> List[MediaInfo]:
        if not self._enabled:
            return []
        headers = {"Accept": "application/json"}
        if self._authorization:
            auth = self._authorization.strip()
            headers["Authorization"] = auth if auth.lower().startswith("bearer ") else f"Bearer {auth}"
        req = RequestUtils(ua=settings.NORMAL_USER_AGENT, headers=headers)
        resp = req.get_res(f"https://api.bgm.tv/search/subject/%E9%87%8C%E7%95%AA")
        if not resp:
            return []
        try:
            data = resp.json()
        except Exception:
            return []
        items = data.get("list") or []
        medias = [MediaInfo(bangumi_info=info) for info in items]
        return medias