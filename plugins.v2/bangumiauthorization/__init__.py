from typing import Any, Dict, List, Tuple, Optional
from datetime import datetime
import json

from app.core.config import settings
from app.plugins import _PluginBase
from app.utils.http import RequestUtils, AsyncRequestUtils
from app.core.meta import MetaBase
from app.core.context import MediaInfo
from app.log import logger


class BangumiAuthorization(_PluginBase):
    plugin_name = "BangumiAuthorization"
    plugin_desc = "为 Bangumi 搜索附加 Authorization"
    plugin_order = 99
    plugin_version = "1.1.0"
    plugin_author = "踏马奔腾"
    plugin_icon = "https://raw.githubusercontent.com/jxxghp/MoviePilot-Plugins/main/icons/bangumi.png"

    _enabled: bool = False
    _authorization: str = ""

    def _headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {"Accept": "application/json"}
        if self._authorization:
            auth = self._authorization.strip()
            headers["Authorization"] = auth if auth.lower().startswith("bearer ") else f"Bearer {auth}"
        return headers

    def init_plugin(self, config: dict = None):
        if config:
            self._enabled = bool(config.get("enabled", False))
            self._authorization = str(config.get("authorization", "") or "")

    def get_state(self) -> bool:
        return self._enabled

    def get_api(self) -> List[Dict[str, Any]]:
        return [
            {
                "path": "/refresh_bangumi",
                "endpoint": self._refresh_bangumi,
                "methods": ["GET"],
                "auth": "apikey",
                "summary": "刷新 Bangumi 授权配置",
                "description": "重新加载并生效插件配置",
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
        return [
            {
                "component": "VRow",
                "content": [
                    {
                        "component": "VCol",
                        "props": {"cols": 12},
                        "content": [
                            {
                                "component": "VAlert",
                                "props": {
                                    "type": "info",
                                    "variant": "tonal",
                                    "text": "需要创建 Bangumi Authorization 令牌"
                                }
                            }
                        ]
                    },
                    {
                        "component": "VCol",
                        "props": {"cols": 12},
                        "content": [
                            {
                                "component": "VBtn",
                                "props": {
                                    "href": "https://next.bgm.tv/demo/access-token/create",
                                    "target": "_blank",
                                    "rel": "noopener",
                                    "color": "primary"
                                },
                                "text": "前往创建令牌"
                            }
                        ]
                    }
                ]
            }
        ]

    def get_module(self) -> Dict[str, Any]:
        return {
            "search_medias": self._search_medias,
            "async_search_medias": self._async_search_medias,
            "scrape_metadata": self._scrape_metadata,
            "async_scrape_metadata": self._async_scrape_metadata,
            "bangumi_info": self._bangumi_info,
            "async_bangumi_info": self._async_bangumi_info,
            "recognize_media": self._recognize_media,
            "async_recognize_media": self._async_recognize_media,
        }

    def stop_service(self):
        pass

    def _search_medias(self, meta: MetaBase) -> Optional[List[MediaInfo]]:
        if not self._enabled:
            return None
        if not meta or not meta.name:
            return []
        url = f"https://api.bgm.tv/search/subject/{meta.name}"
        req = RequestUtils(ua=settings.NORMAL_USER_AGENT, headers=self._headers())
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
        req = RequestUtils(ua=settings.NORMAL_USER_AGENT, headers=self._headers())
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
        req = AsyncRequestUtils(ua=settings.NORMAL_USER_AGENT, headers=self._headers())
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
        req = AsyncRequestUtils(ua=settings.NORMAL_USER_AGENT, headers=self._headers())
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

    def _recognize_media(self, bangumiid: int = None, **kwargs) -> Optional[MediaInfo]:
        if not self._enabled:
            return None
        if not bangumiid:
            return None
        info = self._bangumi_info(bangumiid)
        if isinstance(info, MediaInfo):
            return info
        return None

    async def _async_recognize_media(self, bangumiid: int = None, **kwargs) -> Optional[MediaInfo]:
        if not self._enabled:
            return None
        if not bangumiid:
            return None
        info = await self._async_bangumi_info(bangumiid)
        if isinstance(info, MediaInfo):
            return info
        return None

    def _bangumi_info(self, bangumiid: int) -> Optional[MediaInfo]:
        if not self._enabled:
            return None
        if not bangumiid:
            return None
        req = RequestUtils(ua=settings.NORMAL_USER_AGENT, headers=self._headers())
        resp = req.get_res(
            f"https://api.bgm.tv/v0/subjects/{bangumiid}"
        )
        data = None
        if resp and resp.status_code == 200:
            try:
                data = resp.json()
            except Exception:
                data = None
        return MediaInfo(bangumi_info=data) if isinstance(data, dict) else None

    async def _async_bangumi_info(self, bangumiid: int) -> Optional[MediaInfo]:
        if not self._enabled:
            return None
        if not bangumiid:
            return None
        req = AsyncRequestUtils(ua=settings.NORMAL_USER_AGENT, headers=self._headers())
        resp = await req.get_res(
            f"https://api.bgm.tv/v0/subjects/{bangumiid}"
        )
        data = None
        if resp and resp.status_code == 200:
            try:
                data = resp.json()
            except Exception:
                data = None
        return MediaInfo(bangumi_info=data) if isinstance(data, dict) else None

    def _refresh_bangumi(self, **kwargs) -> Dict[str, Any]:
        cfg = self.get_config(self.__class__.__name__) or {"enabled": False, "authorization": ""}
        try:
            self.init_plugin(cfg)
            return {"ok": True, "enabled": self._enabled}
        except Exception:
            return {"ok": False}