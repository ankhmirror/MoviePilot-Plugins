from typing import Any, Dict, List, Tuple, Optional

from app.core.config import settings
from app.plugins import _PluginBase
from app.utils.http import RequestUtils, AsyncRequestUtils
from app.core.meta import MetaBase
from app.core.context import MediaInfo


class BangumiCookie(_PluginBase):
    plugin_name = "BangumiCookie"
    plugin_desc = "为 Bangumi 搜索附加 Cookie"
    plugin_order = 99
    plugin_version = "1.0.0"
    plugin_author = "User"
    plugin_icon = "https://raw.githubusercontent.com/jxxghp/MoviePilot-Plugins/main/icons/bangumi.png"

    _enabled: bool = False
    _cookie: str = ""

    def init_plugin(self, config: dict = None):
        if config:
            self._enabled = bool(config.get("enabled", False))
            self._cookie = str(config.get("cookie", "") or "")

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
                                        "component": "VTextField",
                                        "props": {
                                            "model": "cookie",
                                            "label": "Bangumi Cookie",
                                            "clearable": True,
                                        },
                                    }
                                ],
                            },
                        ],
                    }
                ],
            }
        ], {"enabled": False, "cookie": ""}

    def get_page(self) -> List[dict]:
        return []

    def get_module(self) -> Dict[str, Any]:
        return {
            "search_medias": self._search_medias,
            "async_search_medias": self._async_search_medias,
        }

    def stop_service(self):
        pass

    def _search_medias(self, meta: MetaBase) -> Optional[List[MediaInfo]]:
        if not self._enabled:
            return None
        if not meta:
            return []
        mediaid = str(getattr(meta, "mediaid", "") or "")
        if mediaid.startswith("bangumi:"):
            sid = mediaid.split(":", 1)[1]
            if not sid:
                return []
            req = RequestUtils(ua=settings.NORMAL_USER_AGENT, cookies=self._cookie)
            dresp = req.get_res(f"https://api.bgm.tv/subject/{sid}")
            if not dresp:
                return []
            try:
                dinfo = dresp.json()
            except Exception:
                return []
            medias = [MediaInfo(bangumi_info=dinfo)]
            if meta.begin_season and medias:
                try:
                    import cn2an
                    season_str = cn2an.an2cn(meta.begin_season, "low")
                    for m in medias:
                        if m.type and m.type.value == "电视剧":
                            m.title = f"{m.title} 第{season_str}季"
                            m.season = meta.begin_season
                except Exception:
                    for m in medias:
                        if m.type and m.type.value == "电视剧":
                            m.season = meta.begin_season
            return medias
        if not meta.name:
            return []
        url = f"https://api.bgm.tv/search/subject/{meta.name}"
        req = RequestUtils(ua=settings.NORMAL_USER_AGENT, cookies=self._cookie)
        resp = req.get_res(url)
        if not resp:
            return []
        try:
            data = resp.json()
        except Exception:
            return []
        items = data.get("list") or []
        medias = [MediaInfo(bangumi_info=info) for info in items]
        if meta.begin_season and medias:
            try:
                import cn2an
                season_str = cn2an.an2cn(meta.begin_season, "low")
                for m in medias:
                    if m.type and m.type.value == "电视剧":
                        m.title = f"{m.title} 第{season_str}季"
                        m.season = meta.begin_season
            except Exception:
                for m in medias:
                    if m.type and m.type.value == "电视剧":
                        m.season = meta.begin_season
        return medias

    async def _async_search_medias(self, meta: MetaBase) -> Optional[List[MediaInfo]]:
        if not self._enabled:
            return None
        if not meta:
            return []
        mediaid = str(getattr(meta, "mediaid", "") or "")
        if mediaid.startswith("bangumi:"):
            sid = mediaid.split(":", 1)[1]
            if not sid:
                return []
            req = AsyncRequestUtils(ua=settings.NORMAL_USER_AGENT, cookies=self._cookie)
            dresp = await req.get_res(f"https://api.bgm.tv/subject/{sid}")
            if not dresp:
                return []
            try:
                dinfo = dresp.json()
            except Exception:
                return []
            medias = [MediaInfo(bangumi_info=dinfo)]
            if meta.begin_season and medias:
                try:
                    import cn2an
                    season_str = cn2an.an2cn(meta.begin_season, "low")
                    for m in medias:
                        if m.type and m.type.value == "电视剧":
                            m.title = f"{m.title} 第{season_str}季"
                            m.season = meta.begin_season
                except Exception:
                    for m in medias:
                        if m.type and m.type.value == "电视剧":
                            m.season = meta.begin_season
            return medias
        if not meta.name:
            return []
        url = f"https://api.bgm.tv/search/subject/{meta.name}"
        req = AsyncRequestUtils(ua=settings.NORMAL_USER_AGENT, cookies=self._cookie)
        resp = await req.get_res(url)
        if not resp:
            return []
        try:
            data = resp.json()
        except Exception:
            return []
        items = data.get("list") or []
        medias = [MediaInfo(bangumi_info=info) for info in items]
        if meta.begin_season and medias:
            try:
                import cn2an
                season_str = cn2an.an2cn(meta.begin_season, "low")
                for m in medias:
                    if m.type and m.type.value == "电视剧":
                        m.title = f"{m.title} 第{season_str}季"
                        m.season = meta.begin_season
            except Exception:
                for m in medias:
                    if m.type and m.type.value == "电视剧":
                        m.season = meta.begin_season
        return medias