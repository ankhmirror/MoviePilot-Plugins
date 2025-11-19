from typing import Any, Dict, List, Tuple, Optional
from datetime import datetime

from app.core.config import settings
from app.plugins import _PluginBase
from app.utils.http import RequestUtils, AsyncRequestUtils
from app.core.meta import MetaBase
from app.core.context import MediaInfo


class BangumiCookie(_PluginBase):
    plugin_name = "BangumiCookie"
    plugin_desc = "为 Bangumi 搜索附加 Authorization"
    plugin_order = 99
    plugin_version = "1.1.0"
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

    def get_page(self) -> List[dict]:
        return []

    def get_module(self) -> Dict[str, Any]:
        return {
            "search_medias": self._search_medias,
            "async_search_medias": self._async_search_medias,
            "scrape_metadata": self._scrape_metadata,
            "async_scrape_metadata": self._async_scrape_metadata,
            "bangumi_info": self._bangumi_info,
            "async_bangumi_info": self._async_bangumi_info,
        }

    def stop_service(self):
        pass

    def _search_medias(self, meta: MetaBase) -> Optional[List[MediaInfo]]:
        if not self._enabled:
            return None
        if not meta or not meta.name:
            return []
        url = f"https://api.bgm.tv/search/subject/{meta.name}"
        _auth = (self._authorization or "").strip()
        if _auth and not _auth.lower().startswith("bearer "):
            _auth = f"Bearer {_auth}"
        _headers = {"Authorization": _auth, "Accept": "application/json"} if _auth else {"Accept": "application/json"}
        req = RequestUtils(ua=settings.NORMAL_USER_AGENT, headers=_headers)
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

    def _scrape_metadata(self, meta: MetaBase) -> Optional[List[MediaInfo]]:
        if not self._enabled:
            return None
        _auth = (self._authorization or "").strip()
        if _auth and not _auth.lower().startswith("bearer "):
            _auth = f"Bearer {_auth}"
        _headers = {"Authorization": _auth, "Accept": "application/json"} if _auth else {"Accept": "application/json"}
        req = RequestUtils(ua=settings.NORMAL_USER_AGENT, headers=_headers)
        mediaid = getattr(meta, "mediaid", None)
        details: List[MediaInfo] = []
        if mediaid:
            try:
                sid = str(mediaid).split(":", 1)[-1]
                dresp = req.get_res(f"https://api.bgm.tv/subject/{sid}")
                if dresp:
                    dinfo = dresp.json()
                    details.append(MediaInfo(bangumi_info=dinfo))
            except Exception:
                return []
        else:
            if not meta or not meta.name:
                return []
            url = f"https://api.bgm.tv/search/subject/{meta.name}"
            resp = req.get_res(url)
            if not resp:
                return []
            try:
                data = resp.json()
            except Exception:
                return []
            items = data.get("list") or []
            for info in items:
                sid = (info or {}).get("id")
                if not sid:
                    continue
                dresp = req.get_res(f"https://api.bgm.tv/subject/{sid}")
                if not dresp:
                    continue
                try:
                    dinfo = dresp.json()
                except Exception:
                    continue
                details.append(MediaInfo(bangumi_info=dinfo))
        if meta.begin_season and details:
            try:
                import cn2an
                season_str = cn2an.an2cn(meta.begin_season, "low")
                for m in details:
                    if m.type and m.type.value == "电视剧":
                        m.title = f"{m.title} 第{season_str}季"
                        m.season = meta.begin_season
            except Exception:
                for m in details:
                    if m.type and m.type.value == "电视剧":
                        m.season = meta.begin_season
        return details

    async def _async_search_medias(self, meta: MetaBase) -> Optional[List[MediaInfo]]:
        if not self._enabled:
            return None
        if not meta or not meta.name:
            return []
        url = f"https://api.bgm.tv/search/subject/{meta.name}"
        _auth = (self._authorization or "").strip()
        if _auth and not _auth.lower().startswith("bearer "):
            _auth = f"Bearer {_auth}"
        _headers = {"Authorization": _auth, "Accept": "application/json"} if _auth else {"Accept": "application/json"}
        req = AsyncRequestUtils(ua=settings.NORMAL_USER_AGENT, headers=_headers)
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

    async def _async_scrape_metadata(self, meta: MetaBase) -> Optional[List[MediaInfo]]:
        if not self._enabled:
            return None
        _auth = (self._authorization or "").strip()
        if _auth and not _auth.lower().startswith("bearer "):
            _auth = f"Bearer {_auth}"
        _headers = {"Authorization": _auth, "Accept": "application/json"} if _auth else {"Accept": "application/json"}
        req = AsyncRequestUtils(ua=settings.NORMAL_USER_AGENT, headers=_headers)
        mediaid = getattr(meta, "mediaid", None)
        details: List[MediaInfo] = []
        if mediaid:
            try:
                sid = str(mediaid).split(":", 1)[-1]
                dresp = await req.get_res(f"https://api.bgm.tv/subject/{sid}")
                if dresp:
                    dinfo = dresp.json()
                    details.append(MediaInfo(bangumi_info=dinfo))
            except Exception:
                return []
        else:
            if not meta or not meta.name:
                return []
            url = f"https://api.bgm.tv/search/subject/{meta.name}"
            resp = await req.get_res(url)
            if not resp:
                return []
            try:
                data = resp.json()
            except Exception:
                return []
            items = data.get("list") or []
            for info in items:
                sid = (info or {}).get("id")
                if not sid:
                    continue
                dresp = await req.get_res(f"https://api.bgm.tv/subject/{sid}")
                if not dresp:
                    continue
                try:
                    dinfo = dresp.json()
                except Exception:
                    continue
                details.append(MediaInfo(bangumi_info=dinfo))
        if meta.begin_season and details:
            try:
                import cn2an
                season_str = cn2an.an2cn(meta.begin_season, "low")
                for m in details:
                    if m.type and m.type.value == "电视剧":
                        m.title = f"{m.title} 第{season_str}季"
                        m.season = meta.begin_season
            except Exception:
                for m in details:
                    if m.type and m.type.value == "电视剧":
                        m.season = meta.begin_season
        return details

    def _bangumi_info(self, bangumiid: int) -> Optional[dict]:
        if not self._enabled:
            return None
        if not bangumiid:
            return None
        _auth = (self._authorization or "").strip()
        if _auth and not _auth.lower().startswith("bearer "):
            _auth = f"Bearer {_auth}"
        _headers = {"Authorization": _auth, "Accept": "application/json"} if _auth else {"Accept": "application/json"}
        req = RequestUtils(ua=settings.NORMAL_USER_AGENT, headers=_headers)
        resp = req.get_res(
            f"https://api.bgm.tv/v0/subjects/{bangumiid}",
            params={"_ts": datetime.strftime(datetime.now(), "%Y%m%d")},
        )
        if not resp:
            return None
        try:
            return resp.json()
        except Exception:
            return None

    async def _async_bangumi_info(self, bangumiid: int) -> Optional[dict]:
        if not self._enabled:
            return None
        if not bangumiid:
            return None
        _auth = (self._authorization or "").strip()
        if _auth and not _auth.lower().startswith("bearer "):
            _auth = f"Bearer {_auth}"
        _headers = {"Authorization": _auth, "Accept": "application/json"} if _auth else {"Accept": "application/json"}
        req = AsyncRequestUtils(ua=settings.NORMAL_USER_AGENT, headers=_headers)
        resp = await req.get_res(
            f"https://api.bgm.tv/v0/subjects/{bangumiid}",
            params={"_ts": datetime.strftime(datetime.now(), "%Y%m%d")},
        )
        if not resp:
            return None
        try:
            return resp.json()
        except Exception:
            return None