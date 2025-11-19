from typing import Any, Dict, List, Tuple, Optional
import re
from urllib.parse import quote

from app.core.config import settings
from app.plugins import _PluginBase
from app.utils.http import RequestUtils, AsyncRequestUtils
from app.core.meta import MetaBase
from app.core.context import MediaInfo


class JavBus(_PluginBase):
    plugin_name = "JavBus"
    plugin_desc = "JavBus 媒体数据源"
    plugin_order = 90
    plugin_version = "1.0.0"
    plugin_author = "黄垚淮"
    plugin_icon = "https://www.javbus.com/favicon.ico"

    _enabled: bool = False

    def init_plugin(self, config: dict = None):
        if config:
            self._enabled = bool(config.get("enabled", False))

    def get_state(self) -> bool:
        return self._enabled

    def get_api(self) -> List[Dict[str, Any]]:
        return [
            {
                "path": "/refresh_javbus",
                "endpoint": self._refresh_javbus,
                "methods": ["GET"],
                "auth": "apikey",
                "summary": "刷新 JavBus 插件配置",
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
                            }
                        ],
                    }
                ],
            }
        ], {"enabled": False}

    def get_page(self) -> List[dict]:
        return []

    def get_module(self) -> Dict[str, Any]:
        return {
            "search_medias": self._search_medias,
            "async_search_medias": self._async_search_medias,
            "scrape_metadata": self._scrape_metadata,
            "async_scrape_metadata": self._async_scrape_metadata,
            "recognize_media": self._recognize_media,
            "async_recognize_media": self._async_recognize_media,
        }

    def stop_service(self):
        pass

    def _build_search_items(self, html: str) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        for m in re.finditer(r'<a[^>]*class=\"movie-box\"[^>]*href=\"https?://www\.javbus\.com/([A-Za-z0-9\-]+)\"[^>]*>([\s\S]*?)</a>', html):
            code = m.group(1)
            block = m.group(2)
            title_m = re.search(r'title=\"([^\"]+)\"', block)
            img_m = re.search(r'<img[^>]*src=\"([^\"]+)\"', block)
            title = title_m.group(1) if title_m else code
            image = img_m.group(1) if img_m else ""
            items.append({
                "id": code,
                "name": title,
                "images": {"large": image, "small": image},
                "url": f"https://www.javbus.com/{code}"
            })
        return items

    def _build_detail_info(self, html: str, code: str) -> Dict[str, Any]:
        title_m = re.search(r"<h3[^>]*>([^<]+)</h3>", html)
        title = title_m.group(1).strip() if title_m else code
        date_m = re.search(r"發行日期\s*[:：]?\s*([0-9]{4}-[0-9]{2}-[0-9]{2})", html)
        date = date_m.group(1) if date_m else ""
        poster_m = re.search(r"<a[^>]*class=\"bigImage\"[^>]*href=\"([^\"]+)\"", html)
        poster = poster_m.group(1) if poster_m else ""
        genres = re.findall(r"<a[^>]*href=\"[^\"]*/genre/[^\"]*\"[^>]*>([^<]+)</a>", html)
        actors = re.findall(r"<a[^>]*href=\"[^\"]*/star/[^\"]*\"[^>]*>([^<]+)</a>", html)
        gallery = re.findall(r"<a[^>]*class=\"sample-box\"[^>]*href=\"([^\"]+)\"", html)
        return {
            "id": code,
            "name": title,
            "date": date,
            "images": {"large": poster or (gallery[0] if gallery else ""), "small": poster},
            "genres": genres,
            "actors": actors,
            "screenshots": gallery,
            "url": f"https://www.javbus.com/{code}"
        }

    def _search_medias(self, meta: MetaBase) -> Optional[List[MediaInfo]]:
        if not self._enabled:
            return None
        if not meta or not meta.name:
            return []
        url = f"https://www.javbus.com/search/{quote(meta.name)}"
        req = RequestUtils(ua=settings.NORMAL_USER_AGENT)
        resp = req.get_res(url)
        if not resp:
            return []
        try:
            html = resp.text
        except Exception:
            return []
        items = self._build_search_items(html)
        medias = [MediaInfo(javbus_info=i) for i in items]
        for m in medias:
            m.title = (m.javbus_info or {}).get("name") if hasattr(m, "javbus_info") else (i.get("name") if isinstance(i, dict) else None)
        return medias

    def _scrape_metadata(self, meta: MetaBase) -> Optional[List[MediaInfo]]:
        if not self._enabled:
            return None
        req = RequestUtils(ua=settings.NORMAL_USER_AGENT)
        mediaid = getattr(meta, "mediaid", None)
        details: List[MediaInfo] = []
        if mediaid:
            try:
                code = str(mediaid).split(":", 1)[-1]
                dresp = req.get_res(f"https://www.javbus.com/{code}")
                if dresp:
                    dinfo = self._build_detail_info(dresp.text, code)
                    details.append(MediaInfo(javbus_info=dinfo))
            except Exception:
                return []
        else:
            if not meta or not meta.name:
                return []
            url = f"https://www.javbus.com/search/{quote(meta.name)}"
            resp = req.get_res(url)
            if not resp:
                return []
            try:
                html = resp.text
            except Exception:
                return []
            items = self._build_search_items(html)
            for info in items[:10]:
                code = (info or {}).get("id")
                if not code:
                    continue
                dresp = req.get_res(f"https://www.javbus.com/{code}")
                if not dresp:
                    continue
                try:
                    dinfo = self._build_detail_info(dresp.text, code)
                except Exception:
                    continue
                details.append(MediaInfo(javbus_info=dinfo))
        for m in details:
            if hasattr(m, "javbus_info") and isinstance(m.javbus_info, dict):
                m.title = m.javbus_info.get("name")
        return details

    async def _async_search_medias(self, meta: MetaBase) -> Optional[List[MediaInfo]]:
        if not self._enabled:
            return None
        if not meta or not meta.name:
            return []
        url = f"https://www.javbus.com/search/{quote(meta.name)}"
        req = AsyncRequestUtils(ua=settings.NORMAL_USER_AGENT)
        resp = await req.get_res(url)
        if not resp:
            return []
        try:
            html = resp.text
        except Exception:
            return []
        items = self._build_search_items(html)
        medias = [MediaInfo(javbus_info=i) for i in items]
        for m in medias:
            if hasattr(m, "javbus_info") and isinstance(m.javbus_info, dict):
                m.title = m.javbus_info.get("name")
        return medias

    async def _async_scrape_metadata(self, meta: MetaBase) -> Optional[List[MediaInfo]]:
        if not self._enabled:
            return None
        req = AsyncRequestUtils(ua=settings.NORMAL_USER_AGENT)
        mediaid = getattr(meta, "mediaid", None)
        details: List[MediaInfo] = []
        if mediaid:
            try:
                code = str(mediaid).split(":", 1)[-1]
                dresp = await req.get_res(f"https://www.javbus.com/{code}")
                if dresp:
                    dinfo = self._build_detail_info(dresp.text, code)
                    details.append(MediaInfo(javbus_info=dinfo))
            except Exception:
                return []
        else:
            if not meta or not meta.name:
                return []
            url = f"https://www.javbus.com/search/{quote(meta.name)}"
            resp = await req.get_res(url)
            if not resp:
                return []
            try:
                html = resp.text
            except Exception:
                return []
            items = self._build_search_items(html)
            for info in items[:10]:
                code = (info or {}).get("id")
                if not code:
                    continue
                dresp = await req.get_res(f"https://www.javbus.com/{code}")
                if not dresp:
                    continue
                try:
                    dinfo = self._build_detail_info(dresp.text, code)
                except Exception:
                    continue
                details.append(MediaInfo(javbus_info=dinfo))
        for m in details:
            if hasattr(m, "javbus_info") and isinstance(m.javbus_info, dict):
                m.title = m.javbus_info.get("name")
        return details

    def _recognize_media(self, javbus_code: str = None, **kwargs) -> Optional[MediaInfo]:
        if not self._enabled:
            return None
        if not javbus_code:
            return None
        req = RequestUtils(ua=settings.NORMAL_USER_AGENT)
        resp = req.get_res(f"https://www.javbus.com/{javbus_code}")
        if not resp:
            return None
        info = self._build_detail_info(resp.text, javbus_code)
        m = MediaInfo(javbus_info=info)
        if hasattr(m, "javbus_info") and isinstance(m.javbus_info, dict):
            m.title = m.javbus_info.get("name")
        return m

    async def _async_recognize_media(self, javbus_code: str = None, **kwargs) -> Optional[MediaInfo]:
        if not self._enabled:
            return None
        if not javbus_code:
            return None
        req = AsyncRequestUtils(ua=settings.NORMAL_USER_AGENT)
        resp = await req.get_res(f"https://www.javbus.com/{javbus_code}")
        if not resp:
            return None
        info = self._build_detail_info(resp.text, javbus_code)
        m = MediaInfo(javbus_info=info)
        if hasattr(m, "javbus_info") and isinstance(m.javbus_info, dict):
            m.title = m.javbus_info.get("name")
        return m

    def _refresh_javbus(self, **kwargs) -> Dict[str, Any]:
        cfg = self.get_config(self.__class__.__name__) or {"enabled": False}
        try:
            self.init_plugin(cfg)
            return {"ok": True, "enabled": self._enabled}
        except Exception:
            return {"ok": False}