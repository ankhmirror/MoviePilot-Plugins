import re
from html import unescape
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

from app import schemas
from app.core.cache import cached
from app.core.config import settings
from app.core.event import Event, eventmanager
from app.log import logger
from app.plugins import _PluginBase
from app.schemas import DiscoverSourceEventData
from app.schemas.types import ChainEventType
from app.utils.http import RequestUtils

from .ui_generator import hanime_filter_ui


BASE_URL = "https://hanime1.me"
SEARCH_URL = f"{BASE_URL}/search"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/137.0.0.0 Safari/537.36"
    ),
    "Referer": f"{BASE_URL}/",
}
VIDEO_LINK_PATTERN = re.compile(
    r'<a[^>]*class="[^"]*\bvideo-link\b[^"]*"[^>]*href="(?P<href>[^"]*?/watch\?v=[^"]+)"'
    r"[^>]*>(?P<body>.*?)</a>",
    re.IGNORECASE | re.DOTALL,
)
TITLE_PATTERN = re.compile(
    r'<div[^>]*class="[^"]*\btitle\b[^"]*"[^>]*>(?P<title>.*?)</div>',
    re.IGNORECASE | re.DOTALL,
)
IMAGE_PATTERN = re.compile(
    r'<img[^>]*class="[^"]*\bmain-thumb\b[^"]*"[^>]*src="(?P<src>[^"]+)"',
    re.IGNORECASE | re.DOTALL,
)
TAG_PATTERN = re.compile(r"<[^>]+>")
YEAR_PATTERN = re.compile(r"(?P<year>(19|20)\d{2})")


class HanimeDiscover(_PluginBase):
    """
    Hanime 探索插件，让探索支持 Hanime 的数据浏览
    """

    plugin_name = "Hanime探索"
    plugin_desc = "让探索支持 Hanime 的数据浏览"
    plugin_icon = "https://hanime1.me/favicon.ico"
    plugin_version = "1.0.0"
    plugin_author = "TRAE"
    author_url = "https://trae.ai"
    plugin_config_prefix = "hanimediscover_"
    plugin_order = 99
    auth_level = 1

    _enabled = False

    def init_plugin(self, config: dict = None) -> None:
        """
        根据配置初始化插件启用状态

        :param config (dict): 插件配置字典
        """
        if config:
            self._enabled = config.get("enabled", False)

        if "vdownload.hembed.com" not in settings.SECURITY_IMAGE_DOMAINS:
            settings.SECURITY_IMAGE_DOMAINS.append("vdownload.hembed.com")

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
                "path": "/hanime_discover",
                "endpoint": self.hanime_discover,
                "methods": ["GET"],
                "summary": "Hanime 探索数据源",
                "description": "获取 Hanime 探索数据",
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
                    }
                ],
            }
        ], {"enabled": False}

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
        return re.sub(r"\s+", " ", unescape(TAG_PATTERN.sub("", text))).strip()

    @staticmethod
    def _extract_media_id(detail_url: str) -> str:
        """
        从详情链接提取媒体 ID

        :param detail_url (str): 详情页链接

        :return str: 媒体 ID
        """
        media_ids = parse_qs(urlparse(detail_url).query).get("v", [])
        return media_ids[0] if media_ids else detail_url

    @staticmethod
    def _extract_year(date_text: Optional[str]) -> Optional[str]:
        """
        从年份筛选值提取年份

        :param date_text (str): 年份筛选值

        :return str: 提取到的年份
        """
        if not date_text:
            return None

        match = YEAR_PATTERN.search(date_text)
        if not match:
            return None
        return match.group("year")

    @cached(region="hanime_discover", ttl=1800, skip_none=True)
    def __request(self, genre: str = None, sort: str = None, date: str = None, page: int = 1) -> str:
        """
        请求 Hanime 搜索页

        :param genre (str): 类别
        :param sort (str): 排序
        :param date (str): 年份
        :param page (int): 页码

        :return str: 搜索页 HTML
        """
        params = {}
        if genre:
            params["genre"] = genre
        if sort:
            params["sort"] = sort
        if date:
            params["date"] = date
        if page > 1:
            params["page"] = page

        request_url = SEARCH_URL
        if params:
            request_url = f"{SEARCH_URL}?{urlencode(params)}"

        res = RequestUtils(headers=HEADERS).get_res(request_url)
        if res is None:
            raise ConnectionError("无法连接 Hanime，请检查网络连接")
        if not res.ok:
            raise ValueError(f"请求 Hanime 失败：{res.status_code}")
        return res.text

    def _parse_videos(self, html: str, date: str = None) -> List[schemas.MediaInfo]:
        """
        解析 Hanime 搜索结果

        :param html (str): 搜索页 HTML
        :param date (str): 年份筛选值

        :return List: 媒体信息列表
        """
        results: List[schemas.MediaInfo] = []
        seen_ids: Set[str] = set()
        year = self._extract_year(date)

        for match in VIDEO_LINK_PATTERN.finditer(html):
            body = match.group("body")
            title_match = TITLE_PATTERN.search(body)
            image_match = IMAGE_PATTERN.search(body)

            if not title_match or not image_match:
                continue

            detail_url = urljoin(BASE_URL, unescape(match.group("href")))
            media_id = self._extract_media_id(detail_url)
            if media_id in seen_ids:
                continue

            title = self._strip_html(title_match.group("title"))
            poster_path = urljoin(BASE_URL, unescape(image_match.group("src")))
            if not title or not poster_path:
                continue

            seen_ids.add(media_id)
            media_info = schemas.MediaInfo(
                type="电视剧",
                title=title,
                mediaid_prefix="hanime",
                media_id=media_id,
                poster_path=poster_path,
            )
            if year:
                media_info.year = year
                media_info.title_year = f"{title} ({year})"
            results.append(media_info)

        return results

    def hanime_discover(
        self,
        genre: str = "裏番",
        sort: str = "本日排行",
        date: str = None,
        page: int = 1,
        count: int = 20,
    ) -> List[schemas.MediaInfo]:
        """
        获取 Hanime 探索数据

        :param genre (str): 类别
        :param sort (str): 排序
        :param date (str): 年份
        :param page (int): 页码
        :param count (int): 返回数量

        :return List: 媒体信息列表
        """
        try:
            html = self.__request(genre=genre, sort=sort, date=date, page=page)
            results = self._parse_videos(html=html, date=date)
            return results[:count]
        except Exception as err:
            logger.error("获取 Hanime 数据失败: %s", err, exc_info=True)
            return []

    @staticmethod
    def hanime_filter_ui() -> List[dict]:
        """
        Hanime 过滤参数 UI 配置

        :return List: 前端筛选 UI 列表
        """
        return hanime_filter_ui()

    @eventmanager.register(ChainEventType.DiscoverSource)
    def discover_source(self, event: Event) -> None:
        """
        监听探索数据源事件，注册 Hanime 数据源

        :param event (Event): 事件对象
        """
        if not self._enabled:
            return

        event_data: DiscoverSourceEventData = event.event_data
        hanime_source = schemas.DiscoverMediaSource(
            name="Hanime",
            mediaid_prefix="hanime",
            api_path=(
                f"plugin/HanimeDiscover/hanime_discover?apikey={settings.API_TOKEN}"
            ),
            filter_params={
                "genre": "裏番",
                "sort": "本日排行",
                "date": None,
            },
            filter_ui=self.hanime_filter_ui(),
        )

        if event_data.extra_sources is None:
            event_data.extra_sources = [hanime_source]
        else:
            event_data.extra_sources.append(hanime_source)

    def stop_service(self) -> None:
        """
        退出插件
        """
        pass
