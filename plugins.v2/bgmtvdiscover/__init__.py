import re
from html import unescape
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote, unquote, urlencode, urljoin

from app import schemas
from app.core.cache import cached
from app.core.config import settings
from app.core.event import Event, eventmanager
from app.log import logger
from app.plugins import _PluginBase
from app.schemas import DiscoverSourceEventData
from app.schemas.types import ChainEventType
from app.utils.http import RequestUtils

from .ui_generator import bgm_filter_ui


BASE_URL = "https://bgm.tv"
TAG_URL = f"{BASE_URL}/anime/tag"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/137.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": f"{BASE_URL}/",
}

TAG_PATTERN = re.compile(r"<[^>]+>")
YEAR_PATTERN = re.compile(r"(?P<year>(19|20)\\d{2})")
ITEM_PATTERN = re.compile(
    r'<li[^>]*id="item_(?P<id>\\d+)"[^>]*>(?P<body>.*?)</li>',
    re.IGNORECASE | re.DOTALL,
)
TITLE_PATTERN = re.compile(
    r'<a[^>]*href="(?P<href>/subject/\\d+[^"]*)"[^>]*>(?P<title>.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
IMAGE_PATTERN = re.compile(
    r'<img[^>]*src="(?P<src>[^"]+)"[^>]*>',
    re.IGNORECASE | re.DOTALL,
)
INFO_PATTERN = re.compile(
    r'<small[^>]*class="[^"]*fade[^"]*"[^>]*>(?P<info>.*?)</small>',
    re.IGNORECASE | re.DOTALL,
)


class BgmTvDiscover(_PluginBase):
    """
    Bangumi(bgm.tv) 标签探索插件，让探索支持按标签浏览动画条目
    """

    plugin_name = "Bangumi标签探索"
    plugin_desc = "让探索支持 bgm.tv 标签页的数据浏览"
    plugin_icon = f"{BASE_URL}/img/favicon.ico"
    plugin_version = "1.0.0"
    plugin_author = "TRAE"
    author_url = "https://trae.ai"
    plugin_config_prefix = "bgmtvdiscover_"
    plugin_order = 99
    auth_level = 1

    _enabled = False
    _cookie: Optional[str] = None
    _use_proxy = True
    _proxy: Optional[str] = None

    def init_plugin(self, config: dict = None) -> None:
        """
        根据配置初始化插件启用状态

        :param config (dict): 插件配置字典
        """
        if config:
            self._enabled = config.get("enabled", False)
            self._cookie = (config.get("cookie") or "").strip() or None
            self._use_proxy = config.get("use_proxy", True)
            self._proxy = (config.get("proxy") or "").strip() or None

        for host in ("bgm.tv", "lain.bgm.tv"):
            if host not in settings.SECURITY_IMAGE_DOMAINS:
                settings.SECURITY_IMAGE_DOMAINS.append(host)

    def get_state(self) -> bool:
        """
        返回插件是否已启用

        :return bool: 插件启用状态
        """
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        """
        返回插件命令列表

        :return List: 命令列表
        """
        pass

    def get_api(self) -> List[Dict[str, Any]]:
        """
        返回插件 API 端点列表

        :return List: API 端点列表
        """
        return [
            {
                "path": "/bgm_discover",
                "endpoint": self.bgm_discover,
                "methods": ["GET"],
                "summary": "Bangumi 标签探索数据源",
                "description": "获取 bgm.tv 标签页的探索数据",
            }
        ]

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        """
        拼装插件配置页面

        :return Tuple: 页面配置与默认数据
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
                                        "props": {
                                            "model": "enabled",
                                            "label": "启用插件",
                                        },
                                    }
                                ],
                            }
                        ],
                    },
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
                                            "text": (
                                                "bgm.tv 的部分标签内容可能需要登录或触发风控"
                                                " 可尝试配置代理或从浏览器复制 Cookie"
                                            ),
                                        },
                                    }
                                ],
                            }
                        ],
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "use_proxy",
                                            "label": "使用全局代理",
                                        },
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
                                            "model": "proxy",
                                            "label": "自定义代理（可选）",
                                            "placeholder": "http://127.0.0.1:7890",
                                            "clearable": True,
                                        },
                                    }
                                ],
                            },
                        ],
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "cookie",
                                            "label": "bgm.tv Cookie（可选）",
                                            "placeholder": "chii_auth=...; chii_sid=...",
                                            "clearable": True,
                                        },
                                    }
                                ],
                            }
                        ],
                    },
                ],
            }
        ], {"enabled": False, "use_proxy": True, "proxy": "", "cookie": ""}

    def _build_proxies(self) -> Optional[Dict[str, str]]:
        """
        构造请求代理配置

        :return Dict: 代理配置
        """
        if self._proxy:
            return {"http": self._proxy, "https": self._proxy}
        if not self._use_proxy:
            return None
        return settings.PROXY if getattr(settings, "PROXY", None) else None

    def _build_headers(self) -> Dict[str, str]:
        """
        构造请求头

        :return Dict: 请求头
        """
        headers = dict(HEADERS)
        if self._cookie:
            headers["Cookie"] = self._cookie
        return headers

    def get_page(self) -> List[dict]:
        """
        返回插件静态页面列表

        :return List: 静态页面列表
        """
        pass

    @staticmethod
    def _strip_html(text: str) -> str:
        """
        清理 HTML 文本

        :param text (str): 原始 HTML 文本

        :return str: 清理后的纯文本
        """
        return re.sub(r"\\s+", " ", unescape(TAG_PATTERN.sub("", text))).strip()

    @staticmethod
    def _normalize_poster_url(src: str) -> str:
        """
        规范化封面图片地址

        :param src (str): 原始图片地址

        :return str: 完整图片地址
        """
        src = unescape(src).strip()
        if src.startswith("//"):
            return f"https:{src}"
        if src.startswith("/"):
            return urljoin(BASE_URL, src)
        return src

    @staticmethod
    def _extract_year(info_text: Optional[str]) -> Optional[str]:
        """
        从条目信息中提取年份

        :param info_text (str): 条目信息文本

        :return str: 年份
        """
        if not info_text:
            return None
        match = YEAR_PATTERN.search(info_text)
        if not match:
            return None
        return match.group("year")

    @cached(region="bgm_tv_discover", ttl=1800, skip_none=True)
    def __request(self, tag: str, sort: str = "rank", page: int = 1) -> str:
        """
        请求 bgm.tv 标签列表页

        :param tag (str): 标签名
        :param sort (str): 排序字段
        :param page (int): 页码

        :return str: 页面 HTML
        """
        normalized_tag = unquote(tag or "").strip() or "里番"
        request_url = f"{TAG_URL}/{quote(normalized_tag)}"
        params = {}
        if sort:
            params["sort"] = sort
        if page > 1:
            params["page"] = page
        if params:
            request_url = f"{request_url}?{urlencode(params)}"

        res = RequestUtils(
            headers=self._build_headers(),
            proxies=self._build_proxies(),
        ).get_res(request_url)
        if res is None:
            raise ConnectionError("无法连接 bgm.tv，请检查网络连接")
        if not res.ok:
            if res.status_code in (401, 403):
                raise ValueError(
                    "请求 bgm.tv 失败：可能需要登录或触发风控，请尝试配置代理或 Cookie"
                )
            raise ValueError(f"请求 bgm.tv 失败：{res.status_code}")
        return res.text

    def _parse_items(self, html: str) -> List[schemas.MediaInfo]:
        """
        解析标签页条目列表

        :param html (str): 页面 HTML

        :return List: 媒体信息列表
        """
        results: List[schemas.MediaInfo] = []
        for match in ITEM_PATTERN.finditer(html or ""):
            subject_id = match.group("id")
            body = match.group("body")

            title_match = TITLE_PATTERN.search(body)
            if not title_match:
                continue

            title = self._strip_html(title_match.group("title"))
            if not title:
                continue

            poster_match = IMAGE_PATTERN.search(body)
            poster_path = (
                self._normalize_poster_url(poster_match.group("src"))
                if poster_match
                else ""
            )
            if not poster_path:
                continue

            info_match = INFO_PATTERN.search(body)
            info_text = self._strip_html(info_match.group("info")) if info_match else None
            year = self._extract_year(info_text)

            media_info = schemas.MediaInfo(
                type="动漫",
                title=title,
                mediaid_prefix="bgm",
                media_id=subject_id,
                poster_path=poster_path,
            )
            if year:
                media_info.year = year
                media_info.title_year = f"{title} ({year})"
            results.append(media_info)
        return results

    def bgm_discover(
        self,
        tag: str = "里番",
        sort: str = "rank",
        page: int = 1,
        count: int = 20,
    ) -> List[schemas.MediaInfo]:
        """
        获取 bgm.tv 标签探索数据

        :param tag (str): 标签名
        :param sort (str): 排序字段
        :param page (int): 页码
        :param count (int): 返回数量

        :return List: 媒体信息列表
        """
        try:
            html = self.__request(tag=tag, sort=sort, page=page)
            results = self._parse_items(html=html)
            return results[:count]
        except Exception as err:
            logger.error("获取 bgm.tv 数据失败: %s", err, exc_info=True)
            return []

    @staticmethod
    def bgm_filter_ui() -> List[dict]:
        """
        Bangumi 标签探索过滤参数 UI 配置

        :return List: 前端筛选 UI 列表
        """
        return bgm_filter_ui()

    @eventmanager.register(ChainEventType.DiscoverSource)
    def discover_source(self, event: Event) -> None:
        """
        监听探索数据源事件，注册 bgm.tv 数据源

        :param event (Event): 事件对象
        """
        if not self._enabled:
            return

        event_data: DiscoverSourceEventData = event.event_data
        bgm_source = schemas.DiscoverMediaSource(
            name="Bangumi(bgm.tv)",
            mediaid_prefix="bgm",
            api_path=(
                f"plugin/BgmTvDiscover/bgm_discover?apikey={settings.API_TOKEN}"
            ),
            filter_params={
                "tag": "里番",
                "sort": "rank",
            },
            filter_ui=self.bgm_filter_ui(),
        )

        if event_data.extra_sources is None:
            event_data.extra_sources = [bgm_source]
        else:
            event_data.extra_sources.append(bgm_source)

    def stop_service(self) -> None:
        """
        退出插件
        """
        pass

