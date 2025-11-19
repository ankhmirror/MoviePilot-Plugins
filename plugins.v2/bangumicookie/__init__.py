from typing import Any, Dict, List, Tuple, Optional
from datetime import datetime
import json

from app.core.config import settings
from app.plugins import _PluginBase
from app.utils.http import RequestUtils, AsyncRequestUtils
from app.core.meta import MetaBase
from app.core.context import MediaInfo
from app.log import logger


class BangumiCookie(_PluginBase):
    """
    功能：为 Bangumi 请求注入 Authorization 令牌
    说明：
      - search/subject 与 v0/subjects 详情在此插件内附加令牌
      - 插件启用后，链路优先命中插件方法，再回退到系统模块
    """
    plugin_name = "BangumiCookie"
    plugin_desc = "为 Bangumi 搜索附加 Authorization"
    plugin_order = 99
    plugin_version = "1.1.0"
    plugin_author = "踏马奔腾"
    plugin_icon = "https://raw.githubusercontent.com/jxxghp/MoviePilot-Plugins/main/icons/bangumi.png"

    _enabled: bool = False
    _authorization: str = ""

    def init_plugin(self, config: dict = None):
        """
        功能：初始化插件配置
        参数：
            config (dict): 插件配置字典（enabled/authorization）
        返回：None
        简单逻辑：读取配置并保存到内部状态
        """
        if config:
            self._enabled = bool(config.get("enabled", False))
            self._authorization = str(config.get("authorization", "") or "")

    def get_state(self) -> bool:
        """
        功能：返回插件启用状态
        返回：bool
        简单逻辑：读取 _enabled 标志
        """
        return self._enabled

    def get_api(self) -> List[Dict[str, Any]]:
        """
        功能：插件 API 声明（当前不提供）
        返回：空列表
        """
        return []

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        """
        功能：生成插件配置表单（启用与 Authorization 令牌）
        返回：表单配置与默认值
        简单逻辑：VSwitch 控制启用，VTextField 输入令牌
        """
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
        """
        功能：插件自定义页面（暂无）
        返回：空列表
        """
        return []

    def get_module(self) -> Dict[str, Any]:
        """
        功能：注册插件拦截的系统模块方法
        返回：方法映射字典
        简单逻辑：识别链优先执行插件方法，再回退系统模块
        """
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
        """
        功能：停止插件服务（预留）
        返回：None
        """
        pass

    def _search_medias(self, meta: MetaBase) -> Optional[List[MediaInfo]]:
        """
        功能：使用 Authorization 令牌搜索番剧
        参数：
            meta (MetaBase): 识别元数据（含名称/季）
        返回：MediaInfo 列表或 None（不拦截）
        简单逻辑：请求 search/subject，构造 MediaInfo 列表并补季信息
        """
        if not self._enabled:
            return None
        if not meta or not meta.name:
            return []
        # 请求搜索接口并附加令牌
        url = f"https://api.bgm.tv/search/subject/{meta.name}"
        req = RequestUtils(ua=settings.NORMAL_USER_AGENT, headers={"Authorization": self._authorization} if self._authorization else None)
        resp = req.get_res(url)
        if not resp:
            return []
        try:
            data = resp.json()
        except Exception:
            return []
        items = data.get("list") or []
        medias = [MediaInfo(bangumi_info=info) for info in items]
        # 补季信息
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
        """
        功能：补抓元数据详情（同步）
        参数：
            meta (MetaBase): 识别元数据（mediaid 或名称）
        返回：MediaInfo 列表或 None（不拦截）
        简单逻辑：按 ID 直接请求 subject/:id；否则通过搜索列表逐条请求详情
        """
        if not self._enabled:
            return None
        req = RequestUtils(ua=settings.NORMAL_USER_AGENT, headers={"Authorization": self._authorization} if self._authorization else None)
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
        # 补季信息
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
        """
        功能：使用 Authorization 令牌搜索番剧（异步）
        参数：
            meta (MetaBase): 识别元数据
        返回：MediaInfo 列表或 None
        简单逻辑：同同步版本
        """
        if not self._enabled:
            return None
        if not meta or not meta.name:
            return []
        url = f"https://api.bgm.tv/search/subject/{meta.name}"
        req = AsyncRequestUtils(ua=settings.NORMAL_USER_AGENT, headers={"Authorization": self._authorization} if self._authorization else None)
        resp = await req.get_res(url)
        if not resp:
            return []
        try:
            data = resp.json()
        except Exception:
            return []
        items = data.get("list") or []
        medias = [MediaInfo(bangumi_info=info) for info in items]
        # 补季信息
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
        """
        功能：补抓元数据详情（异步）
        参数：
            meta (MetaBase): 识别元数据
        返回：MediaInfo 列表或 None
        简单逻辑：同同步版本
        """
        if not self._enabled:
            return None
        req = AsyncRequestUtils(ua=settings.NORMAL_USER_AGENT, headers={"Authorization": self._authorization} if self._authorization else None)
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
        # 补季信息
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
        """
        功能：获取 Bangumi 详情（同步，v0 接口）
        参数：
            bangumiid (int): 番组 ID
        返回：MediaInfo 或 None
        简单逻辑：调用 v0/subjects/:id；无数据返回 None
        """
        if not self._enabled:
            return None
        if not bangumiid:
            return None
        # 首选 v0 接口（附加 Authorization）
        headers = {"Accept": "application/json"}
        if self._authorization:
            auth = self._authorization.strip()
            headers["Authorization"] = auth if auth.lower().startswith("bearer ") else f"Bearer {auth}"
        req = RequestUtils(ua=settings.NORMAL_USER_AGENT, headers=headers)
        logger.info(f"[bangumicookie] AUTH header present: {'YES' if self._authorization else 'NO'} scheme: {headers.get('Authorization','None').split()[0]} url: https://api.bgm.tv/v0/subjects/{bangumiid}")
        resp = req.get_res(
            f"https://api.bgm.tv/v0/subjects/{bangumiid}"
        )
        if resp:
            try:
                logger.info(f"[bangumicookie] v0 response status: {resp.status_code}")
            except Exception:
                pass
        data = None
        if resp and resp.status_code == 200:
            try:
                data = resp.json()
            except Exception:
                data = None
        if isinstance(data, dict):
            try:
                logger.info(f"[bangumicookie] v0 response body: {json.dumps(data, ensure_ascii=False)[:2000]}")
            except Exception:
                pass
        return MediaInfo(bangumi_info=data) if isinstance(data, dict) else None

    async def _async_bangumi_info(self, bangumiid: int) -> Optional[MediaInfo]:
        """
        功能：获取 Bangumi 详情（异步，v0 接口）
        参数：
            bangumiid (int): 番组 ID
        返回：MediaInfo 或 None
        简单逻辑：调用 v0/subjects/:id；无数据返回 None
        """
        if not self._enabled:
            return None
        if not bangumiid:
            return None
        # 首选 v0 接口（附加 Authorization）
        headers = {"Accept": "application/json"}
        if self._authorization:
            auth = self._authorization.strip()
            headers["Authorization"] = auth if auth.lower().startswith("bearer ") else f"Bearer {auth}"
        req = AsyncRequestUtils(ua=settings.NORMAL_USER_AGENT, headers=headers)
        logger.info(f"[bangumicookie] AUTH header present: {'YES' if self._authorization else 'NO'} scheme: {headers.get('Authorization','None').split()[0]} url: https://api.bgm.tv/v0/subjects/{bangumiid}")
        resp = await req.get_res(
            f"https://api.bgm.tv/v0/subjects/{bangumiid}"
        )
        if resp:
            try:
                logger.info(f"[bangumicookie] v0 response status: {resp.status_code}")
            except Exception:
                pass
        data = None
        if resp and resp.status_code == 200:
            try:
                data = resp.json()
            except Exception:
                data = None
        if isinstance(data, dict):
            try:
                logger.info(f"[bangumicookie] v0 response body: {json.dumps(data, ensure_ascii=False)[:2000]}")
            except Exception:
                pass
        return MediaInfo(bangumi_info=data) if isinstance(data, dict) else None