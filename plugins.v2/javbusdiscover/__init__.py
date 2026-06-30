import asyncio
import re
from html import unescape
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import quote, urljoin, urlparse

from fastapi import Response

from app import schemas
from app.core.cache import cached
from app.core.config import settings
from app.core.context import MediaInfo
from app.core.event import Event, eventmanager
from app.core.meta import MetaBase
from app.log import logger
from app.plugins import _PluginBase
from app.schemas import DiscoverSourceEventData
from app.schemas.types import ChainEventType
from app.utils.http import RequestUtils

from .ui_generator import javbus_filter_ui


BASE_URL = "https://www.javbus.com"
UNCENSORED_URL = f"{BASE_URL}/uncensored"
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
IMAGE_PROXY_PREFIX = "/api/v1/plugin/JavbusDiscover/javbus_image?url="

MOVIE_BOX_PATTERN = re.compile(
    r'<a(?=[^>]*class="[^"]*\bmovie-box\b[^"]*")'
    r'(?=[^>]*href="\s*`?(?P<href>[^"`\s]+)`?\s*")'
    r"[^>]*>(?P<body>.*?)</a>",
    re.IGNORECASE | re.DOTALL,
)
IMG_SRC_PATTERN = re.compile(
    r'<img[^>]*src="\s*`?(?P<src>[^"`\s]+)`?\s*"[^>]*>',
    re.IGNORECASE | re.DOTALL,
)
IMG_TITLE_PATTERN = re.compile(
    r'<img[^>]*title="\s*`?(?P<title>[^"`]+)`?\s*"[^>]*>',
    re.IGNORECASE | re.DOTALL,
)
CODE_DATE_PATTERN = re.compile(
    r"<date>(?P<code>[^<]+)</date>\s*/\s*<date>(?P<release>[^<]+)</date>",
    re.IGNORECASE | re.DOTALL,
)
TITLE_SPAN_PATTERN = re.compile(
    r"<span>(?P<title>.*?)(?:<br\s*/?>)",
    re.IGNORECASE | re.DOTALL,
)
TAG_PATTERN = re.compile(r"<[^>]+>")
YEAR_PATTERN = re.compile(r"(?P<year>(19|20)\d{2})")
JAV_CODE_PATTERN = re.compile(
    r"(?P<prefix>[A-Za-z]{2,10})[\s\-_]?(?P<number>\d{2,5})",
    re.IGNORECASE,
)
DETAIL_TITLE_PATTERN = re.compile(
    r"<title>\s*(?P<code>[A-Za-z0-9\-]+)\s+(?P<title>.*?)\s+-\s+JavBus</title>",
    re.IGNORECASE | re.DOTALL,
)
DETAIL_POSTER_PATTERN = re.compile(
    r'<a[^>]*class="[^"]*\bbigImage\b[^"]*"[^>]*href="(?P<href>[^"]+)"',
    re.IGNORECASE | re.DOTALL,
)
DETAIL_RELEASE_PATTERN = re.compile(
    r'<p><span class="header">[^<]*(?:Release Date|發行日期|推出日期)[^<]*</span>\s*(?P<date>\d{4}-\d{2}-\d{2})</p>',
    re.IGNORECASE | re.DOTALL,
)


class JavbusDiscover(_PluginBase):
    """
    JavBus 探索插件，让探索支持 JavBus 的数据浏览
    """

    plugin_name = "JAVBUS探索"
    plugin_desc = "让探索支持 JavBus 的数据浏览"
    plugin_icon = "https://www.javbus.com/favicon.ico"
    plugin_version = "1.1.2"
    plugin_author = "TRAE"
    author_url = "https://trae.ai"
    plugin_config_prefix = "javbusdiscover_"
    plugin_order = 99
    auth_level = 1

    _enabled = False
    _recognize_media = False
    _cookie: Optional[str] = None
    _use_proxy = False
    _proxy: Optional[str] = None
    _uncensored_site = False

    def init_plugin(self, config: dict = None) -> None:
        """
        根据配置初始化插件启用状态

        :param config (dict): 插件配置字典
        """
        if config:
            self._enabled = config.get("enabled", False)
            self._recognize_media = config.get("recognize_media", False)
            self._cookie = (config.get("cookie") or "").strip() or None
            self._use_proxy = config.get("use_proxy", False)
            self._proxy = (config.get("proxy") or "").strip() or None
            self._uncensored_site = config.get("uncensored_site", False)

        if "www.javbus.com" not in settings.SECURITY_IMAGE_DOMAINS:
            settings.SECURITY_IMAGE_DOMAINS.append("www.javbus.com")

    def get_state(self) -> bool:
        """
        返回插件是否已启用

        :return bool: 插件启用状态
        """
        return self._enabled

    def get_module(self) -> Dict[str, Any]:
        """
        获取全局模块声明

        :return Dict: 模块声明
        """
        return {
            "search_medias": self._search_medias,
            "async_search_medias": self._async_search_medias,
            "recognize_media": self._recognize_media_by_id,
            "async_recognize_media": self._async_recognize_media_by_id,
        }

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
                "path": "/javbus_discover",
                "endpoint": self.javbus_discover,
                "methods": ["GET"],
                "summary": "JavBus 探索数据源",
                "description": "获取 JavBus 探索数据",
            },
            {
                "path": "/javbus_image",
                "endpoint": self.javbus_image,
                "methods": ["GET"],
                "summary": "JavBus 图片代理",
                "description": "通过插件代理获取 JavBus 图片",
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
                                "props": {"cols": 12, "md": 3},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "enabled",
                                            "label": "启用插件",
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 3},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "recognize_media",
                                            "label": "媒体识别",
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 3},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "use_proxy",
                                            "label": "代理服务器",
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 3},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "uncensored_site",
                                            "label": "资源站点（默认无码）",
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
                                        "component": "VAlert",
                                        "props": {
                                            "type": "info",
                                            "variant": "tonal",
                                            "text": (
                                                "JavBus 可能触发安全验证（403）"
                                                " 可尝试配置代理或从浏览器复制 Cookie（如 cf_clearance）"
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
                                "props": {"cols": 12},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "proxy",
                                            "label": "代理地址（可选）",
                                            "placeholder": "http://127.0.0.1:7890",
                                            "clearable": True,
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
                                        "component": "VTextField",
                                        "props": {
                                            "model": "cookie",
                                            "label": "Cookie（可选）",
                                            "placeholder": "cf_clearance=...; ...",
                                            "clearable": True,
                                        },
                                    }
                                ],
                            }
                        ],
                    },
                ],
            }
        ], {
            "enabled": False,
            "recognize_media": False,
            "use_proxy": False,
            "uncensored_site": False,
            "proxy": "",
            "cookie": "",
        }

    def _build_proxies(self) -> Optional[Dict[str, str]]:
        """
        构造请求代理配置

        :return Dict: 代理配置
        """
        if not self._use_proxy:
            return None
        if self._proxy:
            return {"http": self._proxy, "https": self._proxy}
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

    @staticmethod
    def _build_cached_image_url(image_url: str) -> str:
        """
        构造插件图片代理地址

        :param image_url (str): 原始图片地址

        :return str: 代理后的图片地址
        """
        clean_url = str(image_url or "").strip()
        if not clean_url:
            return ""
        token = quote(str(settings.API_TOKEN or ""), safe="")
        return (
            f"{IMAGE_PROXY_PREFIX}{quote(clean_url, safe='')}"
            f"&apikey={token}"
        )

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
    def _clean_attr_value(value: str) -> str:
        """
        清理 HTML 属性值中的包裹符号

        :param value (str): 原始属性值

        :return str: 清理后的属性值
        """
        return unescape(value).strip().strip("`").strip()

    @staticmethod
    def _extract_media_id(detail_url: str) -> str:
        """
        从详情链接提取媒体 ID

        :param detail_url (str): 详情页链接

        :return str: 媒体 ID
        """
        path = urlparse(detail_url).path.strip("/").strip()
        if not path:
            return detail_url
        return path.split("/")[-1]

    @staticmethod
    def _extract_year(release_date: Optional[str]) -> Optional[str]:
        """
        从发布日期提取年份

        :param release_date (str): 发布日期

        :return str: 年份
        """
        if not release_date:
            return None
        match = YEAR_PATTERN.search(release_date)
        if not match:
            return None
        return match.group("year")

    @staticmethod
    def _build_title(code: Optional[str], title: Optional[str]) -> Optional[str]:
        """
        拼装展示标题

        :param code (str): 番号
        :param title (str): 标题

        :return str: 拼装后的标题
        """
        code_text = (code or "").strip()
        title_text = (title or "").strip()
        if not title_text and not code_text:
            return None
        if not title_text:
            return code_text
        if not code_text:
            return title_text
        if title_text.startswith(code_text):
            return title_text
        return f"{code_text} {title_text}"

    def _append_media_info(
        self,
        href: str,
        body: str,
        seen_ids: Set[str],
        results: List[schemas.MediaInfo],
    ) -> None:
        """
        追加一条媒体信息

        :param href (str): 详情页链接
        :param body (str): 卡片内容 HTML
        :param seen_ids (Set): 已解析媒体 ID 集合
        :param results (List): 媒体信息列表
        """
        detail_url = urljoin(BASE_URL, self._clean_attr_value(href))
        img_src_match = IMG_SRC_PATTERN.search(body or "")
        if not img_src_match:
            return

        img_title_match = IMG_TITLE_PATTERN.search(body or "")
        if img_title_match:
            title_text = self._strip_html(img_title_match.group("title"))
        else:
            span_match = TITLE_SPAN_PATTERN.search(body or "")
            title_text = self._strip_html(span_match.group("title")) if span_match else None

        code_match = CODE_DATE_PATTERN.search(body or "")
        code = self._strip_html(code_match.group("code")) if code_match else None
        release_date = (
            self._strip_html(code_match.group("release")) if code_match else None
        )

        media_id = code or self._extract_media_id(detail_url)
        if media_id in seen_ids:
            return

        poster_url = urljoin(BASE_URL, self._clean_attr_value(img_src_match.group("src")))
        poster_path = self._build_cached_image_url(poster_url)
        title = self._build_title(code=code, title=title_text)
        if not title or not poster_path:
            return

        seen_ids.add(media_id)
        media_info = schemas.MediaInfo(
            type="电影",
            title=title,
            mediaid_prefix="javbus",
            media_id=media_id,
            poster_path=poster_path,
        )

        year = self._extract_year(release_date)
        if year:
            media_info.year = year
            media_info.title_year = f"{title} ({year})"
        results.append(media_info)

    def _parse_movies(self, html: str) -> List[schemas.MediaInfo]:
        """
        解析 JavBus 列表页媒体卡片

        :param html (str): 列表页 HTML

        :return List: 媒体信息列表
        """
        results: List[schemas.MediaInfo] = []
        seen_ids: Set[str] = set()
        for match in MOVIE_BOX_PATTERN.finditer(html or ""):
            self._append_media_info(
                href=match.group("href"),
                body=match.group("body"),
                seen_ids=seen_ids,
                results=results,
            )
        return results

    @staticmethod
    def javbus_filter_ui() -> List[dict]:
        """
        JavBus 过滤参数 UI 配置

        :return List: 前端筛选 UI 列表
        """
        return javbus_filter_ui()

    @staticmethod
    def _category_to_url(category: Optional[str]) -> str:
        """
        将类别转换为列表页 URL

        :param category (str): 类别

        :return str: 列表页 URL
        """
        if (category or "").strip() == "无码":
            return UNCENSORED_URL
        return BASE_URL

    def _build_list_url(self, category: str = "有码", page: int = 1) -> str:
        """
        构造列表页地址

        :param category (str): 类别
        :param page (int): 页码

        :return str: 列表页地址
        """
        base_url = self._category_to_url(category)
        page_number = int(page or 1)
        if page_number <= 1:
            return base_url
        return f"{base_url}/page/{page_number}"

    @cached(region="javbus_discover", ttl=1800, skip_none=True)
    def __request(self, category: str = "有码", page: int = 1) -> str:
        """
        请求 JavBus 列表页

        :param category (str): 类别
        :param page (int): 页码

        :return str: 列表页 HTML
        """
        request_url = self._build_list_url(category=category, page=page)

        res = RequestUtils(
            headers=self._build_headers(),
            proxies=self._build_proxies(),
        ).get_res(request_url)
        if res is None:
            raise ConnectionError("无法连接 JavBus，请检查网络连接")
        if not res.ok:
            if res.status_code == 403:
                raise ValueError(
                    "请求 JavBus 失败：403，可能触发安全验证，请尝试配置代理或 Cookie"
                )
            raise ValueError(f"请求 JavBus 失败：{res.status_code}")
        return res.text

    def javbus_discover(
        self,
        category: str = "有码",
        page: int = 1,
        count: int = 20,
    ) -> List[schemas.MediaInfo]:
        """
        获取 JavBus 探索数据

        :param category (str): 类别
        :param page (int): 页码
        :param count (int): 返回数量

        :return List: 媒体信息列表
        """
        try:
            html = self.__request(category=category, page=page)
            results = self._parse_movies(html=html)
            return results[:count]
        except Exception as err:
            logger.error("获取 JavBus 数据失败: %s", err, exc_info=True)
            return []

    @staticmethod
    def _normalize_jav_code(text: str) -> Optional[str]:
        """
        从文本中提取并归一化番号

        :param text (str): 原始文本

        :return str: 归一化番号
        """
        if not text:
            return None
        match = JAV_CODE_PATTERN.search(text)
        if not match:
            return None
        prefix = str(match.group("prefix") or "").upper().strip()
        number = str(match.group("number") or "").strip()
        if not prefix or not number:
            return None
        return f"{prefix}-{number}"

    @staticmethod
    def _schemas_to_context_media(item: schemas.MediaInfo) -> Optional[MediaInfo]:
        """
        将探索媒体信息转换为全局 MediaInfo

        :param item (MediaInfo): 探索媒体信息

        :return MediaInfo: 全局媒体信息
        """
        if item is None:
            return None
        try:
            info = MediaInfo(bangumi_info={})
        except Exception:
            return None

        title = str(getattr(item, "title", "") or "").strip()
        poster = str(getattr(item, "poster_path", "") or "").strip()
        media_id = str(getattr(item, "media_id", "") or "").strip()
        year = str(getattr(item, "year", "") or "").strip()

        if media_id:
            setattr(info, "mediaid_prefix", "javbus")
            setattr(info, "media_id", media_id)
        if title:
            setattr(info, "title", title)
            setattr(info, "original_title", title)
        if poster:
            setattr(info, "poster_path", poster)
        if year:
            setattr(info, "year", year)
        setattr(info, "type", "电影")
        return info

    def _iter_site_prefixes(self) -> List[str]:
        """
        获取站点前缀列表

        :return List: 站点前缀列表
        """
        if self._uncensored_site:
            return ["/uncensored", ""]
        return ["", "/uncensored"]

    @cached(region="javbus_source_html", ttl=1800, skip_none=True)
    def _request_html(self, url: str) -> str:
        """
        请求页面 HTML

        :param url (str): 请求地址

        :return str: HTML 内容
        """
        res = RequestUtils(
            headers=self._build_headers(),
            proxies=self._build_proxies(),
        ).get_res(url)
        if res is None:
            raise ConnectionError("无法连接 JavBus，请检查网络连接")
        if not res.ok:
            if res.status_code == 403:
                raise ValueError(
                    "请求 JavBus 失败：403，可能触发安全验证，请尝试配置代理或 Cookie"
                )
            raise ValueError(f"请求 JavBus 失败：{res.status_code}")
        return res.text

    def javbus_image(self, url: str) -> Response:
        """
        通过插件代理获取 JavBus 图片

        :param url (str): 图片地址

        :return Response: 图片响应
        """
        image_url = str(url or "").strip()
        if not image_url:
            return Response(status_code=404, content=b"")

        try:
            res = RequestUtils(
                headers=self._build_headers(),
                proxies=self._build_proxies(),
            ).get_res(image_url)
            if res is None or not getattr(res, "ok", False):
                logger.warning("JavBus 图片代理失败: `%s`", image_url)
                return Response(status_code=404, content=b"")

            content_type = str(
                getattr(res, "headers", {}).get("Content-Type", "image/jpeg")
            ).strip() or "image/jpeg"
            return Response(
                content=getattr(res, "content", b""),
                media_type=content_type,
                headers={"Cache-Control": "public, max-age=86400"},
            )
        except Exception as err:
            logger.warning("JavBus 图片代理异常: `%s`, %s", image_url, err)
            return Response(status_code=404, content=b"")

    def _parse_detail(self, html: str) -> Optional[Dict[str, str]]:
        """
        解析详情页

        :param html (str): HTML 内容

        :return Dict: 解析结果
        """
        if not html:
            return None
        title_match = DETAIL_TITLE_PATTERN.search(html)
        code = (
            self._normalize_jav_code(title_match.group("code")) if title_match else None
        )
        title = self._strip_html(title_match.group("title")) if title_match else ""

        poster_match = DETAIL_POSTER_PATTERN.search(html)
        poster = ""
        if poster_match:
            poster_url = urljoin(BASE_URL, self._clean_attr_value(poster_match.group("href")))
            poster = self._build_cached_image_url(poster_url)

        release_match = DETAIL_RELEASE_PATTERN.search(html)
        release = release_match.group("date").strip() if release_match else ""

        return {
            "code": code or "",
            "title": title,
            "poster": poster,
            "release": release,
        }

    def _detail_to_mediainfo(self, detail: Dict[str, str]) -> Optional[MediaInfo]:
        """
        将详情转换为 MediaInfo

        :param detail (Dict): 详情信息

        :return MediaInfo: 媒体信息
        """
        if not detail:
            return None
        try:
            info = MediaInfo(bangumi_info={})
        except Exception:
            return None

        code = str(detail.get("code") or "").strip()
        title_text = str(detail.get("title") or "").strip()
        poster = str(detail.get("poster") or "").strip()
        release = str(detail.get("release") or "").strip()

        title = self._build_title(code=code, title=title_text)
        if code:
            setattr(info, "mediaid_prefix", "javbus")
            setattr(info, "media_id", code)
        if title:
            setattr(info, "title", title)
            setattr(info, "original_title", title)
        if poster:
            setattr(info, "poster_path", poster)
        if release:
            setattr(info, "release_date", release)
        year = self._extract_year(release)
        if year:
            setattr(info, "year", year)
        setattr(info, "type", "电影")
        return info

    def _fetch_detail(self, code: str) -> Optional[MediaInfo]:
        """
        获取番号详情

        :param code (str): 番号

        :return MediaInfo: 媒体信息
        """
        normalized = self._normalize_jav_code(code) or str(code or "").strip()
        if not normalized:
            return None

        candidates = [
            f"{BASE_URL}/{normalized}",
            f"{UNCENSORED_URL}/{normalized}",
        ]
        if self._uncensored_site:
            candidates = [candidates[1], candidates[0]]

        for url in candidates:
            try:
                html = self._request_html(url)
                parsed = self._parse_detail(html)
                info = self._detail_to_mediainfo(parsed or {})
                if info and getattr(info, "title", None):
                    return info
            except Exception as err:
                logger.debug("请求 JavBus 详情失败: %s", err)
                continue
        return None

    def _search_by_keyword(self, keyword: str) -> List[MediaInfo]:
        """
        按关键词搜索

        :param keyword (str): 搜索词

        :return List: 媒体信息列表
        """
        keyword = str(keyword or "").strip()
        if not keyword:
            return []

        results: List[MediaInfo] = []
        seen: Set[str] = set()
        keyword_encoded = quote(keyword)

        for prefix in self._iter_site_prefixes():
            url = f"{BASE_URL}{prefix}/search/{keyword_encoded}&type=1"
            try:
                html = self._request_html(url)
            except Exception:
                continue

            schema_items = self._parse_movies(html or "")
            for schema_item in schema_items:
                info = self._schemas_to_context_media(schema_item)
                if not info:
                    continue
                media_id = str(getattr(info, "media_id", "") or "").strip()
                if media_id and media_id in seen:
                    continue
                if media_id:
                    seen.add(media_id)
                results.append(info)

        return results[:20]

    def _search_medias(self, meta: MetaBase) -> Optional[List[MediaInfo]]:
        """
        全局搜索媒体

        :param meta (MetaBase): 媒体元数据

        :return List: 媒体结果
        """
        if not self._enabled:
            return None
        if not meta or not getattr(meta, "name", None):
            return []

        query = str(meta.name).strip()
        code = self._normalize_jav_code(query)
        if code:
            info = self._fetch_detail(code)
            return [info] if info else []
        return self._search_by_keyword(query)

    async def _async_search_medias(self, meta: MetaBase) -> Optional[List[MediaInfo]]:
        """
        异步全局搜索媒体

        :param meta (MetaBase): 媒体元数据

        :return List: 媒体结果
        """
        return await asyncio.to_thread(self._search_medias, meta)

    def _recognize_media_by_id(self, javbusid: str = None, **kwargs) -> Optional[MediaInfo]:
        """
        全局识别媒体

        :param javbusid (str): JavBus 番号

        :return MediaInfo: 媒体信息
        """
        if not self._enabled or not self._recognize_media:
            return None

        candidates: List[str] = []
        if javbusid:
            candidates.append(str(javbusid))
        mediaid = kwargs.get("mediaid")
        if mediaid:
            candidates.append(str(mediaid))
        title = kwargs.get("title")
        if title:
            candidates.append(str(title))
        meta = kwargs.get("meta")
        if meta is not None and getattr(meta, "name", None):
            candidates.append(str(getattr(meta, "name")))

        for text in candidates:
            code = self._normalize_jav_code(text)
            if not code:
                continue
            return self._fetch_detail(code)
        return None

    async def _async_recognize_media_by_id(
        self, javbusid: str = None, **kwargs
    ) -> Optional[MediaInfo]:
        """
        异步全局识别媒体

        :param javbusid (str): JavBus 番号

        :return MediaInfo: 媒体信息
        """
        return await asyncio.to_thread(
            self._recognize_media_by_id, javbusid, **kwargs
        )

    @eventmanager.register(ChainEventType.DiscoverSource)
    def discover_source(self, event: Event) -> None:
        """
        监听探索数据源事件，注册 JavBus 数据源

        :param event (Event): 事件对象
        """
        if not self._enabled:
            return

        event_data: DiscoverSourceEventData = event.event_data
        default_category = "无码" if self._uncensored_site else "有码"
        javbus_source = schemas.DiscoverMediaSource(
            name="JavBus",
            mediaid_prefix="javbus",
            api_path=(
                f"plugin/JavbusDiscover/javbus_discover?apikey={settings.API_TOKEN}"
            ),
            filter_params={"category": default_category},
            filter_ui=self.javbus_filter_ui(),
        )

        if event_data.extra_sources is None:
            event_data.extra_sources = [javbus_source]
        else:
            event_data.extra_sources.append(javbus_source)

    def stop_service(self) -> None:
        """
        退出插件
        """
        pass
