from typing import Any, Dict, List, Optional, Tuple

from app.plugins import _PluginBase
from app.core.config import settings
from app.core.context import MediaInfo, Context
from app.chain.bangumi import BangumiChain
from app.chain.search import SearchChain
from app.schemas.types import MediaType


class BangumiPreciseSearch(_PluginBase):
    plugin_name = "Bangumi精确搜索"
    plugin_desc = "提供以 BangumiID 为入口的精确站点检索"
    plugin_order = 98
    plugin_version = "1.0.0"
    plugin_author = "User"

    _enabled: bool = False

    def init_plugin(self, config: dict = None):
        if config:
            self._enabled = bool(config.get("enabled", False))

    def get_state(self) -> bool:
        return self._enabled

    def get_api(self) -> List[Dict[str, Any]]:
        return [
            {
                "path": "/bangumi_search",
                "endpoint": self.bangumi_search,
                "methods": ["GET"],
                "summary": "Bangumi 精确搜索",
                "description": "以 BangumiID 为入口进行站点资源精确检索",
                "auth": "bear",
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
                            }
                        ],
                    }
                ],
            }
        ], {"enabled": False}

    def get_page(self) -> List[dict]:
        return []

    def stop_service(self):
        pass

    async def bangumi_search(
        self,
        bangumiid: int,
        mtype: Optional[str] = None,
        area: Optional[str] = "title",
        season: Optional[int] = None,
        sites: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not self._enabled:
            return {"success": False, "message": "插件未启用"}

        info = await BangumiChain().async_bangumi_info(bangumiid=bangumiid)
        if not info:
            return {"success": False, "message": "未识别到Bangumi媒体信息"}

        mediainfo = MediaInfo(bangumi_info=info)
        if mtype:
            try:
                mediainfo.type = MediaType(mtype)
            except Exception:
                pass
        else:
            mediainfo.type = MediaType.TV
        if season:
            mediainfo.season = int(season)

        site_list = [int(s) for s in sites.split(",") if s] if sites else None

        contexts: List[Context] = await SearchChain().async_process(
            mediainfo=mediainfo,
            sites=site_list,
            area=area,
            no_exists={bangumiid: {int(season): None}} if season else None,
        ) or []

        if not contexts:
            return {"success": False, "message": "未搜索到任何资源"}

        return {"success": True, "data": [c.to_dict() for c in contexts]}