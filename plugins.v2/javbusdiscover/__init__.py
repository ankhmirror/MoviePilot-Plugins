import asyncio
import inspect
import json
import re
from html import unescape
from typing import Any, Callable, Coroutine, Dict, List, Optional, Set, Tuple
from urllib.parse import quote, urljoin, urlparse

from fastapi import Response

from app import schemas
from app.chain import ChainBase
from app.core.cache import cached
from app.core.config import settings
from app.core.context import MediaInfo
from app.core.event import Event, eventmanager
from app.core.meta import MetaBase
from app.log import logger
from app.plugins import _PluginBase
from app.schemas import DiscoverSourceEventData
from app.schemas.types import ChainEventType, MediaType
from app.utils.http import RequestUtils

from .ui_generator import javbus_filter_ui


DEFAULT_BASE_URL = "https://www.javbus.com"
DEFAULT_ALLOWED_IMAGE_HOSTS = {urlparse(DEFAULT_BASE_URL).netloc}
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
    "Referer": f"{DEFAULT_BASE_URL}/",
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
DETAIL_H3_PATTERN = re.compile(
    r"<h3>\s*(?P<title>.*?)\s*</h3>",
    re.IGNORECASE | re.DOTALL,
)
DETAIL_POSTER_PATTERN = re.compile(
    r'<img[^>]*src="(?P<src>/pics/cover/[^"]+)"[^>]*title="(?P<title>[^"]*)"',
    re.IGNORECASE | re.DOTALL,
)
DETAIL_CODE_PATTERN = re.compile(
    r'<span class="header">識別碼:</span>\s*<span[^>]*>(?P<code>[^<]+)</span>',
    re.IGNORECASE | re.DOTALL,
)
DETAIL_RELEASE_PATTERN = re.compile(
    r'<p><span class="header">[^<]*(?:Release Date|發行日期|推出日期)[^<]*</span>\s*(?P<date>\d{4}-\d{2}-\d{2})</p>',
    re.IGNORECASE | re.DOTALL,
)
DETAIL_RUNTIME_PATTERN = re.compile(
    r'<span class="header">長度:</span>\s*(?P<runtime>[^<]+)</p>',
    re.IGNORECASE | re.DOTALL,
)
DETAIL_DIRECTOR_PATTERN = re.compile(
    r'<span class="header">導演:</span>\s*<a[^>]*>(?P<director>.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
DETAIL_STUDIO_PATTERN = re.compile(
    r'<span class="header">製作商:</span>\s*<a[^>]*>(?P<studio>.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
DETAIL_LABEL_PATTERN = re.compile(
    r'<span class="header">發行商:</span>\s*<a[^>]*>(?P<label>.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
DETAIL_GENRE_PATTERN = re.compile(
    r'<span class="genre">\s*<label>.*?<a[^>]*>(?P<genre>.*?)</a>.*?</label>\s*</span>',
    re.IGNORECASE | re.DOTALL,
)
DETAIL_ACTOR_PATTERN = re.compile(
    r'<div class="star-name">\s*<a[^>]*title="(?P<actor>[^"]+)"',
    re.IGNORECASE | re.DOTALL,
)
MAGNET_ROW_PATTERN = re.compile(
    r"<tr[^>]*>.*?"
    r'href="(?P<link>magnet:[^"]+)".*?>\s*(?P<name>.*?)</a>(?P<extra>.*?)</td>.*?'
    r"<td[^>]*>.*?<a[^>]*>\s*(?P<size>.*?)\s*</a>.*?</td>.*?"
    r"<td[^>]*>.*?<a[^>]*>\s*(?P<date>\d{4}-\d{2}-\d{2})\s*</a>.*?</td>.*?"
    r"</tr>",
    re.IGNORECASE | re.DOTALL,
)
MAGNET_TABLE_PATTERN = re.compile(
    r'<table[^>]*id="magnet-table"[^>]*>(?P<body>.*?)</table>',
    re.IGNORECASE | re.DOTALL,
)
MAGNET_TR_PATTERN = re.compile(
    r"<tr[^>]*>(?P<body>.*?)</tr>",
    re.IGNORECASE | re.DOTALL,
)
MAGNET_TD_PATTERN = re.compile(
    r"<td[^>]*>(?P<body>.*?)</td>",
    re.IGNORECASE | re.DOTALL,
)
MAGNET_LINK_PATTERN = re.compile(
    r'href="(?P<link>magnet:[^"]+)"',
    re.IGNORECASE | re.DOTALL,
)
MAGNET_TAG_PATTERN = re.compile(
    r'<a[^>]*class="[^"]*\bbtn\b[^"]*"[^>]*>(?P<tag>.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)


class JavbusDiscover(_PluginBase):
    """
    JavBus 探索插件，让探索支持 JavBus 的数据浏览
    """

    plugin_name = "JAVBUS探索"
    plugin_desc = "让探索支持 JavBus 的数据浏览"
    plugin_icon = "https://www.javbus.com/favicon.ico"
    plugin_version = "2.0.0"
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
    _site_url: Optional[str] = None
    _recognition_mode = "auxiliary"
    _original_method: Optional[Callable] = None
    _original_async_method: Optional[Callable[..., Coroutine[Any, Any, Optional[MediaInfo]]]] = None

    @staticmethod
    def _extract_method_kwargs(method: Optional[Callable], chain_self, args: tuple, kwargs: dict) -> dict:
        """
        解析链式调用参数

        :param method (Callable): 原始方法
        :param chain_self: 链对象自身
        :param args (tuple): 位置参数
        :param kwargs (dict): 命名参数

        :return dict: 解析后的参数
        """
        if not method:
            return dict(kwargs)

        try:
            signature = inspect.signature(method)
            bound = signature.bind_partial(chain_self, *args, **kwargs)
            arguments = dict(bound.arguments)
            first_param = next(iter(signature.parameters), None)
            if first_param:
                arguments.pop(first_param, None)
            nested_kwargs = arguments.pop("kwargs", None)
            nested_args = arguments.pop("args", None)
            if isinstance(nested_kwargs, dict):
                arguments.update(nested_kwargs)
            if isinstance(nested_args, tuple):
                if nested_args:
                    arguments.setdefault("meta", nested_args[0])
                if len(nested_args) > 1:
                    arguments.setdefault("mtype", nested_args[1])
            return arguments
        except TypeError:
            arguments = dict(kwargs)
            if args:
                arguments.setdefault("meta", args[0])
            if len(args) > 1:
                arguments.setdefault("mtype", args[1])
            return arguments

    @staticmethod
    def _normalize_site_url(site_url: Optional[str]) -> str:
        """
        规范化站点地址

        :param site_url (str): 用户配置的站点地址

        :return str: 规范化后的站点地址
        """
        text = str(site_url or "").strip()
        if not text:
            return DEFAULT_BASE_URL
        if "://" not in text:
            text = f"https://{text}"
        parsed = urlparse(text)
        if not parsed.scheme or not parsed.netloc:
            return DEFAULT_BASE_URL
        return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")

    def _base_url(self) -> str:
        """
        获取当前站点地址

        :return str: 站点地址
        """
        return self._normalize_site_url(self._site_url)

    def _uncensored_url(self) -> str:
        """
        获取无码站点地址

        :return str: 无码站点地址
        """
        return f"{self._base_url()}/uncensored"

    def _allowed_image_hosts(self) -> Set[str]:
        """
        获取允许代理的图片域名

        :return Set[str]: 允许的域名集合
        """
        hosts = set(DEFAULT_ALLOWED_IMAGE_HOSTS)
        host = urlparse(self._base_url()).netloc
        if host:
            hosts.add(host)
        return hosts

    def _refresh_security_image_domains(self) -> None:
        """
        将当前站点域名加入图片白名单
        """
        for host in self._allowed_image_hosts():
            if host and host not in settings.SECURITY_IMAGE_DOMAINS:
                settings.SECURITY_IMAGE_DOMAINS.append(host)

    def init_plugin(self, config: dict = None) -> None:
        """
        根据配置初始化插件启用状态

        :param config (dict): 插件配置字典
        """
        plugin_instance: "JavbusDiscover" = self

        def patched_recognize_media(chain_self, *args, **kwargs):
            if not plugin_instance._original_method:
                return None
            result = plugin_instance._original_method(chain_self, *args, **kwargs)
            if result is None and plugin_instance._enabled and plugin_instance._recognize_media:
                logger.info("通过插件 %s 执行：recognize_media ...", plugin_instance.plugin_name)
                plugin_kwargs = plugin_instance._extract_method_kwargs(
                    plugin_instance._original_method,
                    chain_self,
                    args,
                    kwargs,
                )
                meta = plugin_kwargs.pop("meta", None)
                mtype = plugin_kwargs.pop("mtype", None)
                return plugin_instance._recognize_media_by_id(meta=meta, mtype=mtype, **plugin_kwargs)
            return result

        async def patched_async_recognize_media(chain_self, *args, **kwargs):
            if not plugin_instance._original_async_method:
                return None
            result = await plugin_instance._original_async_method(chain_self, *args, **kwargs)
            if result is None and plugin_instance._enabled and plugin_instance._recognize_media:
                logger.info("通过插件 %s 执行：async_recognize_media ...", plugin_instance.plugin_name)
                plugin_kwargs = plugin_instance._extract_method_kwargs(
                    plugin_instance._original_async_method,
                    chain_self,
                    args,
                    kwargs,
                )
                meta = plugin_kwargs.pop("meta", None)
                mtype = plugin_kwargs.pop("mtype", None)
                return await plugin_instance._async_recognize_media_by_id(meta=meta, mtype=mtype, **plugin_kwargs)
            return result

        setattr(patched_recognize_media, "_patched_by", id(self))
        if getattr(ChainBase.recognize_media, "_patched_by", object()) != id(self):
            self._original_method = getattr(ChainBase, "recognize_media", None)

        setattr(patched_async_recognize_media, "_patched_by", id(self))
        if getattr(ChainBase.async_recognize_media, "_patched_by", object()) != id(self):
            self._original_async_method = getattr(ChainBase, "async_recognize_media", None)

        if config:
            self._enabled = config.get("enabled", False)
            self._recognize_media = config.get("recognize_media", False)
            self._cookie = (config.get("cookie") or "").strip() or None
            self._use_proxy = config.get("use_proxy", False)
            self._proxy = (config.get("proxy") or "").strip() or None
            self._uncensored_site = config.get("uncensored_site", False)
            self._site_url = (config.get("site_url") or "").strip() or None
            self._recognition_mode = str(config.get("recognition_mode") or "auxiliary").strip() or "auxiliary"

        if self._enabled and self._recognize_media and self._recognition_mode == "auxiliary":
            if getattr(ChainBase.recognize_media, "_patched_by", object()) != id(self):
                ChainBase.recognize_media = patched_recognize_media
            if getattr(ChainBase.async_recognize_media, "_patched_by", object()) != id(self):
                ChainBase.async_recognize_media = patched_async_recognize_media
        else:
            if getattr(ChainBase.recognize_media, "_patched_by", object()) == id(self) and self._original_method:
                ChainBase.recognize_media = self._original_method
            if (
                getattr(ChainBase.async_recognize_media, "_patched_by", object()) == id(self)
                and self._original_async_method
            ):
                ChainBase.async_recognize_media = self._original_async_method

        self._refresh_security_image_domains()
        logger.info(
            "JavBus插件已加载: version=%s, enabled=%s, recognize_media=%s, recognition_mode=%s, site_url=%s, uncensored_site=%s, use_proxy=%s",
            self.plugin_version,
            self._enabled,
            self._recognize_media,
            self._recognition_mode,
            self._base_url(),
            self._uncensored_site,
            self._use_proxy,
        )

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
        modules = {
            "search_medias": self._search_medias,
            "async_search_medias": self._async_search_medias,
            "scrape_metadata": self._scrape_metadata,
            "async_scrape_metadata": self._async_scrape_metadata,
        }
        if self._recognize_media and self._recognition_mode == "hijacking":
            modules["recognize_media"] = self._recognize_media_by_id
            modules["async_recognize_media"] = self._async_recognize_media_by_id
        return modules

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
                "auth": "bear",
                "summary": "JavBus 探索数据源",
                "description": "获取 JavBus 探索数据",
            },
            {
                "path": "/javbus_image",
                "endpoint": self.javbus_image,
                "methods": ["GET"],
                "allow_anonymous": True,
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
                                            "label": "资源站点",
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
                                                "站点管理：可在下方配置 JAVBUS 域名；"
                                                " 如站点触发安全验证（403），可再配合代理或浏览器 Cookie（如 cf_clearance）"
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
                                            "model": "site_url",
                                            "label": "站点管理 - JAVBUS 域名",
                                            "placeholder": "https://www.javbus.com",
                                            "hint": "留空使用默认站点；填写后探索、搜索、详情和图片代理都会走这个 JAVBUS 域名",
                                            "persistent-hint": True,
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
            "recognition_mode": "auxiliary",
            "use_proxy": False,
            "uncensored_site": False,
            "site_url": "",
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
        headers["Referer"] = f"{self._base_url()}/"
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
        proxy_url = f"{IMAGE_PROXY_PREFIX}{quote(clean_url, safe='')}"
        token = quote(str(settings.API_TOKEN or "").strip(), safe="")
        if token:
            return f"{proxy_url}&apikey={token}"
        return proxy_url

    def _is_allowed_image_url(self, image_url: str) -> bool:
        """
        校验图片代理目标地址是否属于允许的 JavBus 域名。

        :param image_url (str): 图片地址
        :return bool: 是否允许代理
        """
        parsed = urlparse(str(image_url or "").strip())
        if parsed.scheme not in {"http", "https"}:
            return False
        return parsed.netloc in self._allowed_image_hosts()

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
    def _preview_text(text: Any, limit: int = 300) -> str:
        """
        生成日志预览文本，避免整段 HTML 直接刷满终端。

        :param text (Any): 原始内容
        :param limit (int): 最大预览长度

        :return str: 压缩后的日志预览文本
        """
        preview = str(text or "").replace("\r", " ").replace("\n", " ").strip()
        preview = re.sub(r"\s+", " ", preview)
        if len(preview) > limit:
            return f"{preview[:limit]}...(len={len(preview)})"
        return preview

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
    def _extract_runtime_minutes(runtime_text: Optional[str]) -> Optional[int]:
        """
        从时长文本中提取分钟数

        :param runtime_text (str): 原始时长文本

        :return int: 分钟数
        """
        if not runtime_text:
            return None
        match = re.search(r"(\d+)", str(runtime_text))
        if not match:
            return None
        try:
            return int(match.group(1))
        except Exception:
            return None

    @staticmethod
    def _build_named_entries(values: Optional[List[str]] = None, **extra: Any) -> List[Dict[str, Any]]:
        """
        将名称列表转换为主程序常用的结构化数组

        :param values (List[str]): 名称列表
        :param extra (dict): 额外字段

        :return List[Dict[str, Any]]: 结构化结果
        """
        entries: List[Dict[str, Any]] = []
        for value in values or []:
            name = str(value or "").strip()
            if not name:
                continue
            entry: Dict[str, Any] = {"name": name}
            entry.update(extra)
            entries.append(entry)
        return entries

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

    @staticmethod
    def _build_javbus_subscribe_id(code: Optional[str]) -> Optional[str]:
        """
        构造第三方订阅兼容 ID

        :param code (str): JavBus 番号

        :return str: 兼容主程序订阅链的 ID
        """
        code_text = str(code or "").strip()
        if not code_text:
            return None
        return f"javbus:{code_text}"

    @staticmethod
    def _normalize_magnets(items: Optional[List[Dict[str, Any]]]) -> List[Dict[str, str]]:
        """
        规范化磁力链列表

        :param items (List[Dict]): 原始磁力链列表

        :return List[Dict]: 规范化后的磁力链列表
        """
        magnets: List[Dict[str, str]] = []
        for item in items or []:
            url = str((item or {}).get("url") or "").strip()
            if not url:
                continue
            magnets.append(
                {
                    "name": str((item or {}).get("name") or "").strip(),
                    "url": url,
                    "size": str((item or {}).get("size") or "").strip(),
                    "date": str((item or {}).get("date") or "").strip(),
                    "tags": str((item or {}).get("tags") or "").strip(),
                }
            )
        return magnets

    @staticmethod
    def _dump_log_payload(payload: Any) -> str:
        """
        将日志对象转成便于查看的字符串

        :param payload (Any): 日志对象

        :return str: 序列化后的文本
        """
        try:
            return json.dumps(payload, ensure_ascii=False, default=str)
        except Exception:
            return str(payload)

    def _build_fallback_mediainfo(
        self,
        code: str,
        title: Optional[str] = None,
        year: Optional[str] = None,
        poster: Optional[str] = None,
        detail_url: Optional[str] = None,
    ) -> Optional[MediaInfo]:
        """
        构造兜底媒体信息，避免主程序因字段过少无法展示详情

        :param code (str): 番号
        :param title (str): 标题
        :param year (str): 年份
        :param poster (str): 海报
        :param detail_url (str): 详情链接

        :return MediaInfo: 媒体信息
        """
        code_text = str(code or "").strip()
        if not code_text:
            return None
        title_text = str(title or "").strip() or code_text
        poster_text = str(poster or "").strip() or self.plugin_icon
        detail_text = str(detail_url or "").strip()
        if not detail_text:
            candidates = self._build_detail_candidates(code=code_text)
            detail_text = candidates[0] if candidates else f"{self._base_url()}/{code_text}"
        try:
            info = MediaInfo(bangumi_info={})
        except Exception:
            return None

        names = list(dict.fromkeys([name for name in [title_text, code_text] if name]))
        setattr(info, "source", "javbus")
        setattr(info, "type", MediaType.MOVIE)
        setattr(info, "mediaid_prefix", "javbus")
        setattr(info, "media_id", code_text)
        setattr(info, "douban_id", self._build_javbus_subscribe_id(code_text))
        setattr(info, "title", title_text)
        setattr(info, "original_title", title_text)
        setattr(info, "original_name", title_text)
        setattr(info, "detail_link", detail_text)
        setattr(info, "homepage", detail_text)
        setattr(info, "poster_path", poster_text)
        setattr(info, "backdrop_path", poster_text)
        setattr(info, "overview", f"JavBus 媒体 {code_text} 的详情暂未完整获取，当前返回插件兜底数据。")
        setattr(info, "adult", True)
        setattr(info, "status", "Released")
        setattr(info, "vote_average", 0.0)
        setattr(info, "vote_count", 0)
        setattr(info, "popularity", 0.0)
        setattr(info, "release_dates", [])
        setattr(info, "episode_run_time", [])
        setattr(info, "genres", [])
        setattr(info, "genre_ids", [])
        setattr(info, "actors", [])
        setattr(info, "directors", [])
        setattr(info, "production_companies", [])
        setattr(info, "production_countries", [{"name": "日本", "iso_3166_1": "JP"}])
        setattr(info, "origin_country", ["JP"])
        setattr(info, "spoken_languages", [{"english_name": "Japanese", "iso_639_1": "ja", "name": "日语"}])
        setattr(info, "languages", ["ja"])
        setattr(info, "original_language", "ja")
        setattr(info, "category", "JAV")
        setattr(info, "tagline", code_text)
        setattr(info, "number_of_episodes", 1)
        setattr(info, "number_of_seasons", 1)
        setattr(info, "names", names)
        if year:
            setattr(info, "year", str(year))
            setattr(info, "title_year", f"{title_text} ({year})")
        else:
            setattr(info, "title_year", title_text)
        setattr(info, "magnets", [])
        setattr(info, "magnet_count", 0)
        setattr(info, "magnet_links", [])
        logger.info(
            "JavBus默认内容(兜底MediaInfo): %s",
            self._dump_log_payload(info.to_dict()),
        )
        return info

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
        detail_url = urljoin(self._base_url(), self._clean_attr_value(href))
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

        poster_url = urljoin(self._base_url(), self._clean_attr_value(img_src_match.group("src")))
        poster_path = self._build_cached_image_url(poster_url)
        title = self._build_title(code=code, title=title_text)
        if not title or not poster_path:
            return

        seen_ids.add(media_id)
        media_info = schemas.MediaInfo(
            type=MediaType.MOVIE.value,
            source="javbus",
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

    def _category_to_url(self, category: Optional[str]) -> str:
        """
        将类别转换为列表页 URL

        :param category (str): 类别

        :return str: 列表页 URL
        """
        if (category or "").strip() == "无码":
            return self._uncensored_url()
        return self._base_url()

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

    def _schemas_to_context_media(self, item: schemas.MediaInfo) -> Optional[MediaInfo]:
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
            setattr(info, "douban_id", self._build_javbus_subscribe_id(media_id))
            setattr(info, "tagline", media_id)
        setattr(info, "source", "javbus")
        if title:
            setattr(info, "title", title)
            setattr(info, "original_title", title)
            setattr(info, "original_name", title)
        if poster:
            setattr(info, "poster_path", poster)
            setattr(info, "backdrop_path", poster)
        if year:
            setattr(info, "year", year)
            setattr(info, "title_year", f"{title} ({year})" if title else year)
        elif title:
            setattr(info, "title_year", title)
        setattr(info, "detail_link", f"{self._base_url()}/{media_id}" if media_id else None)
        setattr(info, "homepage", f"{self._base_url()}/{media_id}" if media_id else None)
        setattr(info, "names", list(dict.fromkeys([name for name in [title, media_id] if name])))
        setattr(info, "adult", True)
        setattr(info, "status", "Released")
        setattr(info, "vote_average", 0.0)
        setattr(info, "vote_count", 0)
        setattr(info, "popularity", 0.0)
        setattr(info, "category", "JAV")
        setattr(info, "languages", ["ja"])
        setattr(info, "origin_country", ["JP"])
        setattr(info, "production_countries", [{"name": "日本", "iso_3166_1": "JP"}])
        setattr(info, "spoken_languages", [{"english_name": "Japanese", "iso_639_1": "ja", "name": "日语"}])
        setattr(info, "original_language", "ja")
        setattr(info, "number_of_episodes", 1)
        setattr(info, "number_of_seasons", 1)
        setattr(info, "type", MediaType.MOVIE)
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
        logger.info("JavBus详情请求URL: %s", url)
        res = RequestUtils(
            headers=self._build_headers(),
            proxies=self._build_proxies(),
        ).get_res(url)
        if res is None:
            logger.warning("JavBus详情请求失败: url=%s, error=响应为空", url)
            raise ConnectionError("无法连接 JavBus，请检查网络连接")
        if not res.ok:
            logger.warning(
                "JavBus详情请求失败: url=%s, status=%s", url, res.status_code
            )
            if res.status_code == 403:
                raise ValueError(
                    "请求 JavBus 失败：403，可能触发安全验证，请尝试配置代理或 Cookie"
                )
            raise ValueError(f"请求 JavBus 失败：{res.status_code}")
        logger.info(
            "JavBus详情响应: url=%s, status=%s, content_preview=%s",
            url,
            res.status_code,
            self._preview_text(res.text, limit=500),
        )
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
        if not self._is_allowed_image_url(image_url):
            logger.warning(f"JavBus 图片代理地址非法: `{image_url}`")
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

    def _extract_related_items(self, html: str) -> List[Dict[str, str]]:
        """
        提取相关推荐条目

        :param html (str): 详情页 HTML

        :return List: 推荐条目列表
        """
        related_items: List[Dict[str, str]] = []
        marker = 'id="related-waterfall"'
        start = (html or "").find(marker)
        if start < 0:
            return related_items

        related_html = html[start:]
        seen_ids: Set[str] = set()
        for match in MOVIE_BOX_PATTERN.finditer(related_html):
            body = match.group("body")
            href = urljoin(self._base_url(), self._clean_attr_value(match.group("href")))
            media_id = self._extract_media_id(href)
            if not media_id or media_id in seen_ids:
                continue

            title_text = ""
            img_title_match = IMG_TITLE_PATTERN.search(body or "")
            if img_title_match:
                title_text = self._strip_html(img_title_match.group("title"))
            else:
                span_match = TITLE_SPAN_PATTERN.search(body or "")
                if span_match:
                    title_text = self._strip_html(span_match.group("title"))

            img_src_match = IMG_SRC_PATTERN.search(body or "")
            poster = ""
            if img_src_match:
                poster = self._build_cached_image_url(
                    urljoin(self._base_url(), self._clean_attr_value(img_src_match.group("src")))
                )

            if not title_text:
                continue

            seen_ids.add(media_id)
            related_items.append(
                {
                    "id": media_id,
                    "title": title_text,
                    "url": href,
                    "poster": poster,
                }
            )
        return related_items[:12]

    def _extract_magnets(self, html: str) -> List[Dict[str, str]]:
        """
        提取磁力信息

        :param html (str): 详情页 HTML

        :return List: 磁力列表
        """
        magnets: List[Dict[str, str]] = []
        magnet_table_match = MAGNET_TABLE_PATTERN.search(html or "")
        magnet_table_html = magnet_table_match.group("body") if magnet_table_match else ""

        if magnet_table_html:
            for row_match in MAGNET_TR_PATTERN.finditer(magnet_table_html):
                row_html = row_match.group("body") or ""
                cells = [
                    td_match.group("body") or ""
                    for td_match in MAGNET_TD_PATTERN.finditer(row_html)
                ]
                if len(cells) < 3:
                    continue

                first_cell = cells[0]
                link_match = MAGNET_LINK_PATTERN.search(first_cell) or MAGNET_LINK_PATTERN.search(row_html)
                if not link_match:
                    continue

                link = unescape(self._clean_attr_value(link_match.group("link")))
                name_match = re.search(r"<a[^>]*>(?P<name>.*?)</a>", first_cell, re.IGNORECASE | re.DOTALL)
                name = self._strip_html(name_match.group("name")) if name_match else self._strip_html(first_cell)
                size = self._strip_html(cells[1])
                date = self._strip_html(cells[2])
                tags: List[str] = []
                for tag_match in MAGNET_TAG_PATTERN.finditer(first_cell):
                    tag_text = self._strip_html(tag_match.group("tag"))
                    if tag_text and tag_text not in tags:
                        tags.append(tag_text)

                if not link or not name:
                    continue

                magnets.append(
                    {
                        "name": name,
                        "url": link,
                        "size": size,
                        "date": date,
                        "tags": " / ".join(tags),
                    }
                )

            if magnets:
                return magnets
            logger.info(
                "JavBus磁力表格已命中但未解析出数据: preview=%s",
                self._preview_text(magnet_table_html, limit=1200),
            )

        for match in MAGNET_ROW_PATTERN.finditer(html or ""):
            link = unescape(self._clean_attr_value(match.group("link")))
            name = self._strip_html(match.group("name"))
            size = self._strip_html(match.group("size"))
            date = self._strip_html(match.group("date"))
            extra = match.group("extra") or ""
            tags: List[str] = []
            for tag_match in MAGNET_TAG_PATTERN.finditer(extra):
                tag_text = self._strip_html(tag_match.group("tag"))
                if tag_text and tag_text not in tags:
                    tags.append(tag_text)

            if not link or not name:
                continue

            magnets.append(
                {
                    "name": name,
                    "url": link,
                    "size": size,
                    "date": date,
                    "tags": " / ".join(tags),
                }
            )
        return magnets

    def _build_detail_overview(self, detail: Dict[str, Any]) -> str:
        """
        构造详情摘要

        :param detail (Dict): 详情信息

        :return str: 摘要文本
        """
        overview_parts: List[str] = []
        release = str(detail.get("release") or "").strip()
        runtime = str(detail.get("runtime") or "").strip()
        director = str(detail.get("director") or "").strip()
        studio = str(detail.get("studio") or "").strip()
        label = str(detail.get("label") or "").strip()
        actors = detail.get("actors") or []
        genres = detail.get("genres") or []
        magnets = detail.get("magnets") or []
        related_items = detail.get("related") or []

        if release:
            overview_parts.append(f"发行日期 {release}")
        if runtime:
            overview_parts.append(f"时长 {runtime}")
        if director:
            overview_parts.append(f"导演 {director}")
        if studio:
            overview_parts.append(f"制作商 {studio}")
        if label:
            overview_parts.append(f"发行商 {label}")
        if actors:
            overview_parts.append(f"演员 {' / '.join(actors[:5])}")
        if genres:
            overview_parts.append(f"分类 {' / '.join(genres[:8])}")
        if magnets:
            overview_parts.append(f"磁力 {len(magnets)} 条")
        if related_items:
            overview_parts.append(f"推荐 {len(related_items)} 条")
        return " | ".join(overview_parts)

    def _build_detail_candidates(self, code: Optional[str] = None) -> List[str]:
        """
        构造详情页候选地址

        :param code (str): 番号

        :return List: 候选地址列表
        """
        candidates: List[str] = []
        normalized = self._normalize_jav_code(code or "")
        if normalized:
            ordered = [
                f"{self._base_url()}/{normalized}",
                f"{self._uncensored_url()}/{normalized}",
            ]
            if self._uncensored_site:
                ordered = [ordered[1], ordered[0]]
            for url in ordered:
                if url not in candidates:
                    candidates.append(url)
        return candidates

    def _parse_detail(self, html: str, detail_url: str = "") -> Optional[Dict[str, Any]]:
        """
        解析详情页

        :param html (str): HTML 内容
        :param detail_url (str): 详情页地址

        :return Dict: 解析结果
        """
        if not html:
            return None
        code_match = DETAIL_CODE_PATTERN.search(html)
        code = self._normalize_jav_code(code_match.group("code")) if code_match else None

        title_match = DETAIL_H3_PATTERN.search(html) or DETAIL_TITLE_PATTERN.search(html)
        title_raw = title_match.group("title") if title_match else ""
        title_text = self._strip_html(title_raw)
        title = self._build_title(code=code, title=title_text)

        poster_match = DETAIL_POSTER_PATTERN.search(html)
        poster = ""
        if poster_match:
            poster_url = urljoin(self._base_url(), self._clean_attr_value(poster_match.group("src")))
            poster = self._build_cached_image_url(poster_url)

        release_match = DETAIL_RELEASE_PATTERN.search(html)
        release = release_match.group("date").strip() if release_match else ""
        runtime_match = DETAIL_RUNTIME_PATTERN.search(html)
        runtime = self._strip_html(runtime_match.group("runtime")) if runtime_match else ""
        director_match = DETAIL_DIRECTOR_PATTERN.search(html)
        director = (
            self._strip_html(director_match.group("director")) if director_match else ""
        )
        studio_match = DETAIL_STUDIO_PATTERN.search(html)
        studio = self._strip_html(studio_match.group("studio")) if studio_match else ""
        label_match = DETAIL_LABEL_PATTERN.search(html)
        label = self._strip_html(label_match.group("label")) if label_match else ""

        genres: List[str] = []
        for match in DETAIL_GENRE_PATTERN.finditer(html):
            genre = self._strip_html(match.group("genre"))
            if genre and genre not in genres and genre != "多選提交":
                genres.append(genre)

        actors: List[str] = []
        for match in DETAIL_ACTOR_PATTERN.finditer(html):
            actor = self._strip_html(match.group("actor"))
            if actor and actor not in actors:
                actors.append(actor)

        magnets = self._extract_magnets(html)
        related = self._extract_related_items(html)

        detail = {
            "code": code or "",
            "title": title,
            "original_title": title_text,
            "poster": poster,
            "release": release,
            "runtime": runtime,
            "director": director,
            "studio": studio,
            "label": label,
            "genres": genres,
            "actors": actors,
            "magnets": magnets,
            "related": related,
            "detail_url": detail_url,
        }
        detail["overview"] = self._build_detail_overview(detail)
        logger.info(
            "JavBus详情解析结果: url=%s, code=%s, title=%s, release=%s, actors=%s, genres=%s, magnets=%s, related=%s, overview=%s",
            detail_url,
            detail.get("code"),
            self._preview_text(detail.get("title"), limit=120),
            detail.get("release"),
            len(detail.get("actors") or []),
            len(detail.get("genres") or []),
            len(detail.get("magnets") or []),
            len(detail.get("related") or []),
            self._preview_text(detail.get("overview"), limit=180),
        )
        return detail

    def _detail_to_mediainfo(self, detail: Dict[str, Any]) -> Optional[MediaInfo]:
        """
        将详情转换为 MediaInfo

        :param detail (Dict): 详情信息

        :return MediaInfo: 媒体信息
        """
        if not detail:
            return None
        logger.info(
            "JavBus检索到的内容(detail): %s",
            self._dump_log_payload(detail),
        )
        try:
            info = MediaInfo(bangumi_info={})
        except Exception:
            return None

        code = str(detail.get("code") or "").strip()
        title_text = str(detail.get("title") or "").strip()
        original_title = str(detail.get("original_title") or "").strip()
        poster = str(detail.get("poster") or "").strip()
        release = str(detail.get("release") or "").strip()
        runtime_text = str(detail.get("runtime") or "").strip()
        director = str(detail.get("director") or "").strip()
        studio = str(detail.get("studio") or "").strip()
        label = str(detail.get("label") or "").strip()
        overview = str(detail.get("overview") or "").strip()
        detail_url = str(detail.get("detail_url") or "").strip()
        genres = [str(genre or "").strip() for genre in (detail.get("genres") or []) if str(genre or "").strip()]
        actors = [str(actor or "").strip() for actor in (detail.get("actors") or []) if str(actor or "").strip()]
        magnets = self._normalize_magnets(detail.get("magnets") or [])
        related_items = detail.get("related") or []

        title = title_text or self._build_title(code=code, title=original_title)
        backdrop = poster
        runtime = self._extract_runtime_minutes(runtime_text)
        names = list(dict.fromkeys([name for name in [title, original_title, code] if name]))
        production_companies = self._build_named_entries(
            [company for company in [studio, label] if company]
        )
        if code:
            setattr(info, "mediaid_prefix", "javbus")
            setattr(info, "media_id", code)
            setattr(info, "douban_id", self._build_javbus_subscribe_id(code))
        setattr(info, "source", "javbus")
        if title:
            setattr(info, "title", title)
        if original_title:
            setattr(info, "original_title", original_title)
        if detail_url:
            setattr(info, "detail_link", detail_url)
            setattr(info, "homepage", detail_url)
        if poster:
            setattr(info, "poster_path", poster)
        if backdrop:
            setattr(info, "backdrop_path", backdrop)
        if overview:
            setattr(info, "overview", overview)
        setattr(info, "adult", True)
        setattr(info, "status", "Released")
        setattr(info, "vote_average", 0.0)
        setattr(info, "vote_count", len(actors))
        setattr(info, "popularity", float(len(actors) + len(genres)))
        if release:
            setattr(info, "release_date", release)
            setattr(info, "first_air_date", release)
            setattr(info, "last_air_date", release)
            setattr(info, "release_dates", [release])
        if runtime is not None:
            setattr(info, "runtime", runtime)
            setattr(info, "episode_run_time", [runtime])
        if genres:
            setattr(info, "genres", self._build_named_entries(genres))
            setattr(info, "genre_ids", genres)
        if actors:
            setattr(info, "actors", self._build_named_entries(actors))
        if director:
            setattr(info, "directors", self._build_named_entries([director], job="导演"))
        if production_companies:
            setattr(info, "production_companies", production_companies)
        setattr(info, "production_countries", [{"name": "日本", "iso_3166_1": "JP"}])
        setattr(info, "origin_country", ["JP"])
        setattr(info, "spoken_languages", [{"english_name": "Japanese", "iso_639_1": "ja", "name": "日语"}])
        setattr(info, "languages", ["ja"])
        setattr(info, "original_language", "ja")
        setattr(info, "category", "JAV")
        setattr(info, "number_of_episodes", 1)
        setattr(info, "number_of_seasons", 1)
        if title:
            setattr(info, "original_name", title)
        if code:
            setattr(info, "tagline", code)
        if names:
            setattr(info, "names", names)
        setattr(info, "magnets", magnets)
        setattr(info, "magnet_count", len(magnets))
        setattr(info, "magnet_links", [item.get("url") for item in magnets if item.get("url")])
        setattr(info, "related_items", related_items)
        year = self._extract_year(release)
        if year:
            setattr(info, "year", year)
            setattr(info, "title_year", f"{title or original_title} ({year})")
        elif title:
            setattr(info, "title_year", title)
        setattr(info, "type", MediaType.MOVIE)
        logger.info(
            "JavBus默认内容(补全后MediaInfo): %s",
            self._dump_log_payload(info.to_dict()),
        )
        return info

    def _fetch_detail(self, code: str = None) -> Optional[MediaInfo]:
        """
        获取番号详情

        :param code (str): 番号

        :return MediaInfo: 媒体信息
        """
        candidates = self._build_detail_candidates(code=code)
        if not candidates:
            logger.info("JavBus详情候选URL为空: input=%s", code)
            return None

        logger.info("JavBus详情候选URL: code=%s, urls=%s", code, candidates)

        for url in candidates:
            try:
                html = self._request_html(url)
                parsed = self._parse_detail(html, detail_url=url)
                info = self._detail_to_mediainfo(parsed or {})
                if info and getattr(info, "title", None):
                    logger.info(
                        "JavBus详情返回结果: url=%s, media_id=%s, title=%s, year=%s, type=%s",
                        url,
                        getattr(info, "media_id", None),
                        self._preview_text(getattr(info, "title", None), limit=120),
                        getattr(info, "year", None),
                        getattr(getattr(info, "type", None), "value", getattr(info, "type", None)),
                    )
                    return info
                logger.info(
                    "JavBus详情未得到有效媒体信息: url=%s, parsed=%s",
                    url,
                    parsed or {},
                )
            except Exception as err:
                logger.warning("请求 JavBus 详情失败: url=%s, error=%s", url, err)
                continue
        logger.info("JavBus详情所有候选URL均未命中，返回兜底数据: code=%s", code)
        return self._build_fallback_mediainfo(code=code)

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
            url = f"{self._base_url()}{prefix}/search/{keyword_encoded}&type=1"
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
            info = self._fetch_detail(code=code)
            return [info] if info else []
        return self._search_by_keyword(query)

    async def _async_search_medias(self, meta: MetaBase) -> Optional[List[MediaInfo]]:
        """
        异步全局搜索媒体

        :param meta (MetaBase): 媒体元数据

        :return List: 媒体结果
        """
        return await asyncio.to_thread(self._search_medias, meta)

    def _scrape_metadata(self, meta: MetaBase) -> Optional[List[MediaInfo]]:
        """
        全局刮削元数据

        :param meta (MetaBase): 媒体元数据

        :return List: 详情结果
        """
        if not self._enabled:
            return None

        mediaid = getattr(meta, "mediaid", None) if meta else None
        code = self._normalize_jav_code(str(mediaid or ""))
        if not code and meta is not None:
            code = self._normalize_jav_code(str(getattr(meta, "name", "") or ""))

        if code:
            info = self._fetch_detail(code=code)
            return [info] if info else []

        medias = self._search_medias(meta) or []
        details: List[MediaInfo] = []
        seen_ids: Set[str] = set()
        for media in medias[:5]:
            item_code = self._normalize_jav_code(str(getattr(media, "media_id", "") or ""))
            info = self._fetch_detail(code=item_code)
            if not info:
                continue
            item_id = str(getattr(info, "media_id", "") or "").strip()
            if item_id and item_id in seen_ids:
                continue
            if item_id:
                seen_ids.add(item_id)
            details.append(info)
        return details

    async def _async_scrape_metadata(self, meta: MetaBase) -> Optional[List[MediaInfo]]:
        """
        异步全局刮削元数据

        :param meta (MetaBase): 媒体元数据

        :return List: 详情结果
        """
        return await asyncio.to_thread(self._scrape_metadata, meta)

    def _recognize_media_by_id(self, javbusid: str = None, **kwargs) -> Optional[MediaInfo]:
        """
        全局识别媒体

        :param javbusid (str): JavBus 番号

        :return MediaInfo: 媒体信息
        """
        if not self._enabled or not self._recognize_media:
            return None

        meta = kwargs.get("meta")
        logger.info(
            "JavBus识别入参: javbusid=%s, mediaid=%s, title=%s, meta_name=%s, meta_title=%s",
            javbusid,
            kwargs.get("mediaid"),
            self._preview_text(kwargs.get("title"), limit=160),
            self._preview_text(getattr(meta, "name", None), limit=120) if meta else None,
            self._preview_text(getattr(meta, "title", None), limit=160) if meta else None,
        )
        candidates: List[str] = []
        raw_candidates = [
            javbusid,
            kwargs.get("mediaid"),
            kwargs.get("doubanid"),
            kwargs.get("title"),
            getattr(meta, "title", None) if meta is not None else None,
            getattr(meta, "name", None) if meta is not None else None,
        ]
        for item in raw_candidates:
            text = str(item or "").strip()
            if text and text not in candidates:
                candidates.append(text)

        logger.info("JavBus识别检索候选: %s", candidates)

        for text in candidates:
            code = self._normalize_jav_code(text)
            logger.info(
                "JavBus识别检索内容: raw=%s, normalized=%s",
                self._preview_text(text, limit=180),
                code,
            )
            if not code:
                continue
            info = self._fetch_detail(code=code)
            logger.info(
                "JavBus识别最终返回: code=%s, success=%s, title=%s, year=%s",
                code,
                bool(info),
                self._preview_text(getattr(info, "title", None), limit=120) if info else None,
                getattr(info, "year", None) if info else None,
            )
            return info
        logger.info("JavBus识别结束: 未从候选中提取到有效番号")
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
            api_path="plugin/JavbusDiscover/javbus_discover",
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
        if getattr(ChainBase.recognize_media, "_patched_by", object()) == id(self) and self._original_method:
            ChainBase.recognize_media = self._original_method
        if (
            getattr(ChainBase.async_recognize_media, "_patched_by", object()) == id(self)
            and self._original_async_method
        ):
            ChainBase.async_recognize_media = self._original_async_method
