from datetime import datetime
import re
from html import unescape
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse
from urllib.parse import quote

from app.core.cache import cached
from app.core.config import settings
from app.core.context import MediaInfo
from app.core.meta import MetaBase
from app.log import logger
from app.plugins import _PluginBase
from app.utils.http import AsyncRequestUtils, RequestUtils


class HuanLeHuiju(_PluginBase):
    """
    欢乐汇聚插件

    第一版聚焦 Bangumi 数据源，提供全局识别、全局搜索、
    metadata 预览、融合展示与手动刷新能力
    后续可在相同数据结构下继续接入 TMDB、豆瓣等来源
    """

    plugin_name = "欢乐汇聚"
    plugin_desc = "MoviePilot 全局识别与 metadata 融合插件，第一版接入 Bangumi"
    plugin_order = 99
    plugin_version = "1.2.1"
    plugin_author = "踏马奔腾"
    author_url = "https://trae.ai"
    plugin_icon = (
        "https://raw.githubusercontent.com/jxxghp/MoviePilot-Plugins/main/icons/bangumi.png"
    )

    HANIME_BASE_URL = "https://hanime1.me"
    _hanime_headers = {
        "User-Agent": settings.NORMAL_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": f"{HANIME_BASE_URL}/",
    }
    _hanime_title_pattern = re.compile(
        r'<h3[^>]*id="shareBtn-title"[^>]*>(?P<title>.*?)</h3>',
        re.IGNORECASE | re.DOTALL,
    )
    _hanime_series_pattern = re.compile(
        r'<div[^>]*class="hidden-xs"[^>]*>.*?</div>\s*<div[^>]*>(?P<series>.*?)</div>',
        re.IGNORECASE | re.DOTALL,
    )
    _hanime_date_pattern = re.compile(r"(?P<date>\d{4}-\d{2}-\d{2})")
    _hanime_views_pattern = re.compile(
        r"观看次数：(?P<views>[^<\s]+)",
        re.IGNORECASE | re.DOTALL,
    )
    _hanime_desc_pattern = re.compile(
        r'<div[^>]*class="[^"]*\bvideo-caption-text\b[^"]*"[^>]*>(?P<desc>.*?)</div>',
        re.IGNORECASE | re.DOTALL,
    )
    _hanime_og_image_pattern = re.compile(
        r'<meta[^>]*property="\s*og:image\s*"[^>]*content="\s*(?P<src>[^"\s]+)\s*"[^>]*>',
        re.IGNORECASE | re.DOTALL,
    )
    _hanime_tag_pattern = re.compile(
        r'<div[^>]*class="[^"]*\bsingle-video-tag\b[^"]*"[^>]*>.*?<a[^>]*>(?P<tag>.*?)</a>.*?</div>',
        re.IGNORECASE | re.DOTALL,
    )
    _hanime_strip_tag_pattern = re.compile(r"<[^>]+>")

    _enabled: bool = False
    _authorization: str = ""
    _preview_title: str = ""
    _preview_bangumi_id: str = ""
    _preview_hanime_id: str = ""
    _use_cache: bool = True
    _prefer_exact_match: bool = True
    _hanime_cookie: str = ""
    _hanime_use_proxy: bool = True
    _hanime_proxy: str = ""

    def init_plugin(self, config: dict = None) -> None:
        """
        生效插件配置

        :param config (dict): 插件配置
        """
        self._enabled = False
        self._authorization = ""
        self._preview_title = ""
        self._preview_bangumi_id = ""
        self._preview_hanime_id = ""
        self._use_cache = True
        self._prefer_exact_match = True
        self._hanime_cookie = ""
        self._hanime_use_proxy = True
        self._hanime_proxy = ""

        if not config:
            return

        self._enabled = bool(config.get("enabled", False))
        authorization = str(config.get("authorization", "") or "").strip()
        if authorization:
            if authorization.lower().startswith("bearer "):
                self._authorization = authorization
            else:
                self._authorization = f"Bearer {authorization}"
        self._preview_title = str(config.get("preview_title", "") or "").strip()
        self._preview_bangumi_id = str(config.get("preview_bangumi_id", "") or "").strip()
        self._preview_hanime_id = str(config.get("preview_hanime_id", "") or "").strip()
        self._use_cache = bool(config.get("use_cache", True))
        self._prefer_exact_match = bool(config.get("prefer_exact_match", True))
        self._hanime_cookie = str(config.get("hanime_cookie", "") or "").strip()
        self._hanime_use_proxy = bool(config.get("hanime_use_proxy", True))
        self._hanime_proxy = str(config.get("hanime_proxy", "") or "").strip()

    def get_state(self) -> bool:
        """
        获取插件状态

        :return bool: 插件是否启用
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
            "scrape_metadata": self._scrape_metadata,
            "async_scrape_metadata": self._async_scrape_metadata,
            "bangumi_info": self._bangumi_info,
            "async_bangumi_info": self._async_bangumi_info,
            "recognize_media": self._recognize_media,
            "async_recognize_media": self._async_recognize_media,
        }

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        """
        获取插件命令

        :return List: 命令列表
        """
        return []

    def get_api(self) -> List[Dict[str, Any]]:
        """
        获取插件 API

        :return List: API 定义
        """
        return [
            {
                "path": "/refresh_preview",
                "endpoint": self.refresh_preview,
                "methods": ["GET"],
                "summary": "刷新欢乐汇聚预览",
                "description": "按当前插件配置刷新 Bangumi metadata 预览结果",
            },
            {
                "path": "/query_metadata",
                "endpoint": self.query_metadata,
                "methods": ["GET"],
                "summary": "查询融合 metadata",
                "description": "按标题或 Bangumi ID 查询 metadata，并可选保存为详情页预览",
            },
            {
                "path": "/query_hanime",
                "endpoint": self.query_hanime,
                "methods": ["GET"],
                "summary": "查询 Hanime 条目",
                "description": "按 Hanime watch ID 或链接解析标题、简介、标签等信息",
            },
        ]

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        """
        获取插件配置页

        :return Tuple: 配置页面与默认数据
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
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "use_cache",
                                            "label": "启用缓存",
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "prefer_exact_match",
                                            "label": "优先精确匹配",
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
                                            "model": "authorization",
                                            "label": "Bangumi Authorization",
                                            "hint": "可选，填写 Access Token，自动补全 Bearer 前缀",
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
                                "props": {"cols": 12, "md": 6},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "preview_title",
                                            "label": "预览标题",
                                            "hint": "例如 进击的巨人 / 葬送的芙莉莲",
                                            "persistent-hint": True,
                                            "clearable": True,
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "preview_bangumi_id",
                                            "label": "预览 Bangumi ID",
                                            "hint": "填写后优先按 ID 查询",
                                            "persistent-hint": True,
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
                                "props": {"cols": 12, "md": 6},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "preview_hanime_id",
                                            "label": "预览 Hanime ID",
                                            "hint": "对应 https://hanime1.me/watch?v=ID 中的 ID",
                                            "persistent-hint": True,
                                            "clearable": True,
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "hanime_cookie",
                                            "label": "Hanime Cookie（可选）",
                                            "hint": "如触发安全验证（403）可从浏览器复制 cf_clearance 等",
                                            "persistent-hint": True,
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
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "hanime_use_proxy",
                                            "label": "Hanime 使用全局代理",
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
                                            "model": "hanime_proxy",
                                            "label": "Hanime 自定义代理（可选）",
                                            "placeholder": "http://127.0.0.1:7890",
                                            "clearable": True,
                                        },
                                    }
                                ],
                            },
                        ],
                    },
                    {
                        "component": "VAlert",
                        "props": {
                            "type": "info",
                            "variant": "tonal",
                            "text": "当前版本支持 Bangumi 全局识别与搜索，并新增 Hanime 条目解析能力，可用于预览融合效果",
                        },
                    },
                ],
            }
        ], {
            "enabled": False,
            "authorization": "",
            "preview_title": "",
            "preview_bangumi_id": "",
            "preview_hanime_id": "",
            "use_cache": True,
            "prefer_exact_match": True,
            "hanime_cookie": "",
            "hanime_use_proxy": True,
            "hanime_proxy": "",
        }

    def get_page(self) -> List[dict]:
        """
        获取插件详情页

        :return List: 详情页组件配置
        """
        preview = self.get_data("last_preview") or {}
        last_error = self.get_data("last_error")
        query = (preview.get("query") or {}) if isinstance(preview, dict) else {}
        metadata = (preview.get("metadata") or {}) if isinstance(preview, dict) else {}
        ids = metadata.get("ids") or {}
        source_items = metadata.get("sources") or []
        genres = metadata.get("genres") or []
        aliases = metadata.get("aliases") or []
        updated_at = preview.get("updated_at") or "未刷新"
        poster = metadata.get("poster") or ""
        summary = metadata.get("summary") or "暂无简介"
        subtitle = metadata.get("subtitle") or "暂无副标题"
        status_text = "已启用" if self._enabled else "未启用"

        page: List[dict] = [
            {
                "component": "VAlert",
                "props": {
                    "type": "info",
                    "variant": "tonal",
                    "text": (
                        "欢乐汇聚当前为第一版，详情页展示的是 Bangumi 归一化 metadata 结果"
                        " 已预留多数据源融合结构"
                    ),
                },
            },
            {
                "component": "VCard",
                "props": {"class": "mt-3"},
                "content": [
                    {"component": "VCardTitle", "text": "当前状态"},
                    {
                        "component": "VCardText",
                        "content": [
                            {
                                "component": "div",
                                "text": f"插件状态：{status_text}",
                            },
                            {
                                "component": "div",
                                "text": f"预览标题：{self._preview_title or '未配置'}",
                            },
                            {
                                "component": "div",
                                "text": (
                                    f"预览 Bangumi ID：{self._preview_bangumi_id or '未配置'}"
                                ),
                            },
                            {
                                "component": "div",
                                "text": (
                                    f"预览 Hanime ID：{self._preview_hanime_id or '未配置'}"
                                ),
                            },
                            {
                                "component": "div",
                                "text": f"最近刷新：{updated_at}",
                            },
                        ],
                    },
                    {
                        "component": "VCardActions",
                        "content": [
                            {
                                "component": "VBtn",
                                "props": {
                                    "color": "primary",
                                    "variant": "flat",
                                },
                                "text": "刷新预览",
                                "events": {
                                    "click": {
                                        "api": f"plugin/HuanLeHuiju/refresh_preview?apikey={settings.API_TOKEN}",
                                        "method": "get",
                                    }
                                },
                            }
                        ],
                    },
                ],
            },
        ]

        if last_error:
            page.append(
                {
                    "component": "VAlert",
                    "props": {
                        "class": "mt-3",
                        "type": "warning",
                        "variant": "tonal",
                        "text": f"最近一次刷新失败：{last_error}",
                    },
                }
            )

        if not metadata:
            page.append(
                {
                    "component": "VAlert",
                    "props": {
                        "class": "mt-3",
                        "type": "warning",
                        "variant": "tonal",
                        "text": "暂无预览数据，请先在插件配置中填写标题、Bangumi ID 或 Hanime ID，然后点击刷新预览",
                    },
                }
            )
            return page

        metadata_card: List[dict] = [
            {"component": "VCardTitle", "text": metadata.get("title") or "未命名条目"},
            {"component": "VCardSubtitle", "text": subtitle},
        ]

        if poster:
            metadata_card.append(
                {
                    "component": "VImg",
                    "props": {
                        "src": poster,
                        "height": 320,
                        "cover": True,
                    },
                }
            )

        metadata_card.append(
            {
                "component": "VCardText",
                "content": [
                    {
                        "component": "div",
                        "text": (
                            f"查询条件：标题={query.get('title') or '未填写'}"
                            f" / Bangumi ID={query.get('bangumi_id') or '未填写'}"
                            f" / Hanime ID={query.get('hanime_id') or '未填写'}"
                        ),
                    },
                    {
                        "component": "div",
                        "text": f"来源数量：{preview.get('source_count') or 0}",
                    },
                    {
                        "component": "div",
                        "text": f"首播日期：{metadata.get('date') or '未知'}",
                    },
                    {
                        "component": "div",
                        "text": f"评分：{metadata.get('rating') or '暂无'}",
                    },
                    {
                        "component": "div",
                        "text": f"排名：{metadata.get('rank') or '暂无'}",
                    },
                    {
                        "component": "div",
                        "text": f"主标题：{metadata.get('title') or '暂无'}",
                    },
                    {
                        "component": "div",
                        "text": f"原始标题：{metadata.get('original_title') or '暂无'}",
                    },
                    {
                        "component": "div",
                        "text": f"别名：{', '.join(aliases) if aliases else '暂无'}",
                    },
                    {
                        "component": "div",
                        "text": f"分类：{', '.join(genres) if genres else '暂无'}",
                    },
                    {
                        "component": "div",
                        "text": f"Bangumi ID：{ids.get('bangumi') or '暂无'}",
                    },
                    {
                        "component": "div",
                        "text": f"Hanime ID：{ids.get('hanime') or '暂无'}",
                    },
                    {
                        "component": "div",
                        "text": f"数据源：{', '.join(source_items) if source_items else 'Bangumi'}",
                    },
                    {"component": "div", "text": f"简介：{summary}"},
                ],
            }
        )

        page.append(
            {
                "component": "VCard",
                "props": {"class": "mt-3"},
                "content": metadata_card,
            }
        )

        return page

    def stop_service(self) -> None:
        """
        停止插件
        """
        return

    def _headers(self) -> Dict[str, str]:
        """
        生成请求头

        :return Dict: 请求头
        """
        headers = {
            "Accept": "application/json",
            "User-Agent": settings.NORMAL_USER_AGENT,
        }
        if self._authorization:
            headers["Authorization"] = self._authorization
        return headers

    def _build_hanime_headers(self) -> Dict[str, str]:
        """
        生成 Hanime 请求头

        :return Dict: 请求头
        """
        headers = dict(self._hanime_headers)
        if self._hanime_cookie:
            headers["Cookie"] = self._hanime_cookie
        return headers

    def _build_hanime_proxies(self) -> Optional[Dict[str, str]]:
        """
        生成 Hanime 代理配置

        :return Dict: 代理配置
        """
        if self._hanime_proxy:
            return {"http": self._hanime_proxy, "https": self._hanime_proxy}
        if not self._hanime_use_proxy:
            return None
        return settings.PROXY if getattr(settings, "PROXY", None) else None

    @classmethod
    def _strip_hanime_html(cls, text: str) -> str:
        """
        清理 Hanime HTML 文本

        :param text (str): 原始 HTML 文本

        :return str: 清理后的纯文本
        """
        return re.sub(r"\s+", " ", unescape(cls._hanime_strip_tag_pattern.sub("", text))).strip()

    @staticmethod
    def _extract_hanime_watch_id(value: Optional[str]) -> str:
        """
        提取 Hanime watch ID

        :param value (str): watch ID 或链接

        :return str: watch ID
        """
        raw = str(value or "").strip()
        if not raw:
            return ""
        if raw.isdigit():
            return raw
        try:
            parsed = urlparse(raw)
            watch_ids = parse_qs(parsed.query).get("v", [])
            if watch_ids and str(watch_ids[0]).isdigit():
                return str(watch_ids[0])
        except Exception:
            return ""
        return ""

    @staticmethod
    def _extract_title_from_kwargs(kwargs: Dict[str, Any]) -> str:
        """
        从识别参数提取标题

        :param kwargs (Dict): 识别参数

        :return str: 标题
        """
        for key in ["title", "name", "keyword", "key", "file_name", "filename", "raw_title"]:
            value = kwargs.get(key)
            if not value:
                continue
            text = str(value).strip()
            if text:
                return text
        return ""

    def _extract_hanime_watch_id_from_kwargs(self, kwargs: Dict[str, Any]) -> str:
        """
        从识别参数提取 Hanime watch ID

        :param kwargs (Dict): 识别参数

        :return str: watch ID
        """
        for key in [
            "hanime_id",
            "hanimeid",
            "url",
            "link",
            "path",
            "file_path",
            "filepath",
            "original_name",
            "raw",
            "title",
            "name",
        ]:
            value = kwargs.get(key)
            if not value:
                continue
            raw = str(value)
            if "hanime1.me" in raw or "watch?v=" in raw or "hanime:" in raw.lower():
                watch_id = self._extract_hanime_watch_id(raw)
                if watch_id:
                    return watch_id
            if key in {"hanime_id", "hanimeid"}:
                watch_id = self._extract_hanime_watch_id(raw)
                if watch_id:
                    return watch_id
        return ""

    @cached(region="huanlehuiju_hanime_watch", ttl=86400, skip_none=True)
    def _request_hanime_watch(self, watch_id: str) -> Optional[str]:
        """
        请求 Hanime watch 详情页

        :param watch_id (str): watch ID

        :return str: HTML
        """
        request_url = f"{self.HANIME_BASE_URL}/watch?v={watch_id}"
        response = RequestUtils(
            headers=self._build_hanime_headers(),
            proxies=self._build_hanime_proxies(),
        ).get_res(request_url)
        if response is None or not response.ok:
            return None
        return response.text

    def _parse_hanime_watch(self, watch_id: str, html: str) -> Optional[Dict[str, Any]]:
        """
        解析 Hanime watch 详情

        :param watch_id (str): watch ID
        :param html (str): HTML 内容

        :return Dict: 解析结果
        """
        if not html:
            return None

        title_match = self._hanime_title_pattern.search(html)
        title = (
            self._strip_hanime_html(title_match.group("title"))
            if title_match
            else ""
        )

        series_match = self._hanime_series_pattern.search(html)
        series = (
            self._strip_hanime_html(series_match.group("series"))
            if series_match
            else ""
        )

        desc_match = self._hanime_desc_pattern.search(html)
        description = (
            self._strip_hanime_html(desc_match.group("desc"))
            if desc_match
            else ""
        )

        date_match = self._hanime_date_pattern.search(html)
        date_text = date_match.group("date") if date_match else ""

        views_match = self._hanime_views_pattern.search(html)
        views_text = views_match.group("views") if views_match else ""

        og_image_match = self._hanime_og_image_pattern.search(html)
        poster = og_image_match.group("src") if og_image_match else ""

        tags: List[str] = []
        for match in self._hanime_tag_pattern.finditer(html):
            tag_text = self._strip_hanime_html(match.group("tag"))
            tag_text = tag_text.lstrip("#").strip()
            tag_text = re.sub(r"\(\s*\d+\s*\)$", "", tag_text).strip()
            if tag_text and tag_text not in tags:
                tags.append(tag_text)

        return {
            "id": watch_id,
            "url": f"{self.HANIME_BASE_URL}/watch?v={watch_id}",
            "title": title,
            "series": series,
            "description": description,
            "date": date_text,
            "views": views_text,
            "poster": poster,
            "tags": tags,
        }

    def _build_hanime_metadata(self, hanime: Dict[str, Any]) -> Dict[str, Any]:
        """
        构造 Hanime 归一化 metadata

        :param hanime (Dict): Hanime 解析结果

        :return Dict: 归一化结果
        """
        date_text = str(hanime.get("date") or "").strip()
        subtitle_parts = []
        if hanime.get("series"):
            subtitle_parts.append(str(hanime.get("series")))
        if date_text:
            subtitle_parts.append(date_text)
        if hanime.get("views"):
            subtitle_parts.append(f"播放 {hanime.get('views')}")

        title = str(hanime.get("title") or "").strip()
        series = str(hanime.get("series") or "").strip()
        aliases: List[str] = []
        if title:
            aliases.append(title)
        if series and series not in aliases:
            aliases.append(series)

        tags = hanime.get("tags") or []
        genres = [t for t in tags if isinstance(t, str) and t][:12]

        return {
            "title": series or title,
            "subtitle": " / ".join(subtitle_parts) if subtitle_parts else "Hanime",
            "original_title": title,
            "date": date_text,
            "year": date_text.split("-", 1)[0] if date_text else "",
            "rating": "",
            "rank": "",
            "summary": str(hanime.get("description") or "").strip(),
            "poster": str(hanime.get("poster") or "").strip(),
            "genres": genres,
            "aliases": aliases,
            "ids": {
                "hanime": hanime.get("id"),
            },
            "sources": ["Hanime"],
        }

    @staticmethod
    def _season_text(season: Optional[int]) -> Optional[str]:
        """
        获取季文本

        :param season (int): 季号

        :return str: 季文本
        """
        if not season:
            return None
        try:
            season_int = int(season)
        except Exception:
            return None
        if season_int <= 0:
            return None
        return f"第{season_int}季"

    def _apply_season(
        self, medias: Optional[List[MediaInfo]], begin_season: Optional[int]
    ) -> None:
        """
        为结果补充季信息

        :param medias (List): 媒体列表
        :param begin_season (int): 开始季号
        """
        if not medias or not begin_season:
            return
        season_text = self._season_text(begin_season)
        for media in medias:
            try:
                media.season = begin_season
                media_type = getattr(getattr(media, "type", None), "value", None)
                if media_type == "电视剧" and season_text and getattr(media, "title", None):
                    if season_text not in media.title:
                        media.title = f"{media.title} {season_text}"
            except Exception:
                continue

    @staticmethod
    def _normalize_text(text: Optional[str]) -> str:
        """
        规范化文本

        :param text (str): 原始文本

        :return str: 规范化后的文本
        """
        if not text:
            return ""
        lowered = str(text).strip().lower()
        return "".join(char for char in lowered if char.isalnum())

    def _request_json(self, url: str) -> Optional[dict]:
        """
        请求 JSON 数据

        :param url (str): 请求地址

        :return dict: JSON 数据
        """
        response = RequestUtils(
            ua=settings.NORMAL_USER_AGENT,
            headers=self._headers(),
        ).get_res(url)
        if response is None or not response.ok:
            return None
        try:
            payload = response.json()
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None
        return payload

    async def _async_request_json(self, url: str) -> Optional[dict]:
        """
        异步请求 JSON 数据

        :param url (str): 请求地址

        :return dict: JSON 数据
        """
        response = await AsyncRequestUtils(
            ua=settings.NORMAL_USER_AGENT,
            headers=self._headers(),
        ).get_res(url)
        if response is None or not response.ok:
            return None
        try:
            payload = response.json()
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None
        return payload

    @cached(region="huanlehuiju_bangumi_search", ttl=1800, skip_none=True)
    def _cached_search(self, title: str) -> List[dict]:
        """
        使用缓存搜索 Bangumi

        :param title (str): 搜索标题

        :return List: 搜索结果
        """
        return self._search_subjects(title)

    @cached(region="huanlehuiju_bangumi_subject", ttl=1800, skip_none=True)
    def _cached_subject(self, bangumi_id: str) -> Optional[dict]:
        """
        使用缓存获取 Bangumi 条目

        :param bangumi_id (str): Bangumi ID

        :return dict: 条目详情
        """
        return self._fetch_subject_detail(bangumi_id)

    def _search_subjects(self, title: str) -> List[dict]:
        """
        搜索 Bangumi 条目

        :param title (str): 标题

        :return List: 搜索结果
        """
        encoded_title = quote(title)
        data = self._request_json(f"https://api.bgm.tv/search/subject/{encoded_title}")
        items = (data or {}).get("list") or []
        if not isinstance(items, list):
            return []
        return [item for item in items if isinstance(item, dict)]

    async def _async_search_subjects(self, title: str) -> List[dict]:
        """
        异步搜索 Bangumi 条目

        :param title (str): 标题

        :return List: 搜索结果
        """
        encoded_title = quote(title)
        data = await self._async_request_json(
            f"https://api.bgm.tv/search/subject/{encoded_title}"
        )
        items = (data or {}).get("list") or []
        if not isinstance(items, list):
            return []
        return [item for item in items if isinstance(item, dict)]

    def _fetch_subject_detail(self, bangumi_id: str) -> Optional[dict]:
        """
        获取 Bangumi 条目详情

        :param bangumi_id (str): Bangumi ID

        :return dict: 条目详情
        """
        return self._request_json(f"https://api.bgm.tv/v0/subjects/{bangumi_id}")

    async def _async_fetch_subject_detail(self, bangumi_id: str) -> Optional[dict]:
        """
        异步获取 Bangumi 条目详情

        :param bangumi_id (str): Bangumi ID

        :return dict: 条目详情
        """
        return await self._async_request_json(
            f"https://api.bgm.tv/v0/subjects/{bangumi_id}"
        )

    def _pick_best_subject(self, title: str, items: List[dict]) -> Optional[dict]:
        """
        选择最佳 Bangumi 搜索结果

        :param title (str): 查询标题
        :param items (List): 搜索结果

        :return dict: 命中的最佳结果
        """
        if not items:
            return None
        if not self._prefer_exact_match:
            return items[0]

        normalized_query = self._normalize_text(title)
        for item in items:
            names = [
                item.get("name"),
                item.get("name_cn"),
            ]
            for name in names:
                if self._normalize_text(name) == normalized_query:
                    return item
        return items[0]

    @staticmethod
    def _collect_aliases(subject: dict) -> List[str]:
        """
        收集别名

        :param subject (dict): Bangumi 条目详情

        :return List: 别名列表
        """
        aliases: List[str] = []
        for field in ["name", "name_cn"]:
            value = subject.get(field)
            if value and value not in aliases:
                aliases.append(value)
        infobox = subject.get("infobox") or []
        if isinstance(infobox, list):
            for item in infobox:
                if not isinstance(item, dict):
                    continue
                key = str(item.get("key") or "")
                value = item.get("value")
                if key not in {"别名", "中文名"}:
                    continue
                if isinstance(value, str) and value and value not in aliases:
                    aliases.append(value)
                elif isinstance(value, list):
                    for value_item in value:
                        if isinstance(value_item, str) and value_item not in aliases:
                            aliases.append(value_item)
                        elif isinstance(value_item, dict):
                            alias_name = value_item.get("v")
                            if (
                                isinstance(alias_name, str)
                                and alias_name
                                and alias_name not in aliases
                            ):
                                aliases.append(alias_name)
        return aliases

    @staticmethod
    def _collect_genres(subject: dict) -> List[str]:
        """
        收集分类标签

        :param subject (dict): Bangumi 条目详情

        :return List: 分类列表
        """
        tags = subject.get("tags") or []
        genres: List[str] = []
        if not isinstance(tags, list):
            return genres
        for tag in tags[:8]:
            if not isinstance(tag, dict):
                continue
            name = tag.get("name")
            if isinstance(name, str) and name and name not in genres:
                genres.append(name)
        return genres

    @staticmethod
    def _summary_text(subject: dict) -> str:
        """
        生成简介文本

        :param subject (dict): Bangumi 条目详情

        :return str: 简介文本
        """
        summary = str(subject.get("summary", "") or "").strip()
        if not summary:
            return ""
        return " ".join(summary.split())

    def _build_metadata(self, subject: dict) -> Dict[str, Any]:
        """
        构造归一化 metadata

        :param subject (dict): Bangumi 条目详情

        :return Dict: 归一化结果
        """
        rating = subject.get("rating") or {}
        images = subject.get("images") or {}
        title = subject.get("name_cn") or subject.get("name") or ""
        original_title = subject.get("name") or ""
        date_text = subject.get("date") or ""
        subtitle_parts = []
        if original_title and title and original_title != title:
            subtitle_parts.append(original_title)
        if date_text:
            subtitle_parts.append(str(date_text))
        return {
            "title": title,
            "subtitle": " / ".join(subtitle_parts) if subtitle_parts else "Bangumi",
            "original_title": original_title,
            "date": date_text,
            "year": str(date_text).split("-", 1)[0] if date_text else "",
            "rating": rating.get("score") or "",
            "rank": rating.get("rank") or "",
            "summary": self._summary_text(subject),
            "poster": images.get("large")
            or images.get("common")
            or images.get("medium")
            or "",
            "genres": self._collect_genres(subject),
            "aliases": self._collect_aliases(subject),
            "ids": {
                "bangumi": subject.get("id"),
            },
            "sources": ["Bangumi"],
        }

    @staticmethod
    def _merge_unique(items: List[str]) -> List[str]:
        """
        合并去重列表

        :param items (List): 原始列表

        :return List: 去重结果
        """
        merged: List[str] = []
        for item in items:
            if not item:
                continue
            if item not in merged:
                merged.append(item)
        return merged

    def _merge_metadata(
        self,
        bangumi_meta: Optional[Dict[str, Any]] = None,
        hanime_meta: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        融合 metadata

        :param bangumi_meta (Dict): Bangumi metadata
        :param hanime_meta (Dict): Hanime metadata

        :return Dict: 融合结果
        """
        base = bangumi_meta or hanime_meta or {}
        merged = dict(base)

        ids: Dict[str, Any] = {}
        sources: List[str] = []
        aliases: List[str] = []
        genres: List[str] = []

        for meta in [bangumi_meta, hanime_meta]:
            if not meta:
                continue
            ids.update(meta.get("ids") or {})
            sources.extend(meta.get("sources") or [])
            aliases.extend(meta.get("aliases") or [])
            genres.extend(meta.get("genres") or [])

        merged["ids"] = ids
        merged["sources"] = self._merge_unique(sources)
        merged["aliases"] = self._merge_unique(aliases)
        merged["genres"] = self._merge_unique(genres)

        poster = ""
        for meta in [bangumi_meta, hanime_meta]:
            if not meta:
                continue
            poster = poster or str(meta.get("poster") or "").strip()
        merged["poster"] = poster

        summary_parts: List[str] = []
        for meta in [bangumi_meta, hanime_meta]:
            if not meta:
                continue
            text = str(meta.get("summary") or "").strip()
            if text and text not in summary_parts:
                summary_parts.append(text)
        merged["summary"] = "\n\n".join(summary_parts) if summary_parts else ""

        if not merged.get("title"):
            merged["title"] = (
                str((bangumi_meta or {}).get("title") or "").strip()
                or str((hanime_meta or {}).get("title") or "").strip()
            )

        return merged

    def _resolve_subject(
        self,
        title: Optional[str] = None,
        bangumi_id: Optional[str] = None,
    ) -> Tuple[Optional[dict], Optional[str]]:
        """
        解析 Bangumi 条目

        :param title (str): 查询标题
        :param bangumi_id (str): Bangumi ID

        :return Tuple: 条目详情与错误信息
        """
        clean_bangumi_id = str(bangumi_id or "").strip()
        clean_title = str(title or "").strip()
        if clean_bangumi_id:
            subject = (
                self._cached_subject(clean_bangumi_id)
                if self._use_cache
                else self._fetch_subject_detail(clean_bangumi_id)
            )
            if not subject:
                return None, f"未找到 Bangumi 条目 {clean_bangumi_id}"
            return subject, None

        if not clean_title:
            return None, "请先配置预览标题或 Bangumi ID"

        items = (
            self._cached_search(clean_title)
            if self._use_cache
            else self._search_subjects(clean_title)
        )
        subject_brief = self._pick_best_subject(clean_title, items)
        if not subject_brief:
            return None, f"Bangumi 未搜索到 {clean_title}"

        subject_id = subject_brief.get("id")
        if not subject_id:
            return None, "命中条目缺少 Bangumi ID"

        subject = (
            self._cached_subject(str(subject_id))
            if self._use_cache
            else self._fetch_subject_detail(str(subject_id))
        )
        if not subject:
            return None, f"无法获取 Bangumi 条目详情 {subject_id}"
        return subject, None

    async def _async_resolve_subject(
        self,
        title: Optional[str] = None,
        bangumi_id: Optional[str] = None,
    ) -> Tuple[Optional[dict], Optional[str]]:
        """
        异步解析 Bangumi 条目

        :param title (str): 查询标题
        :param bangumi_id (str): Bangumi ID

        :return Tuple: 条目详情与错误信息
        """
        clean_bangumi_id = str(bangumi_id or "").strip()
        clean_title = str(title or "").strip()
        if clean_bangumi_id:
            subject = (
                self._cached_subject(clean_bangumi_id)
                if self._use_cache
                else await self._async_fetch_subject_detail(clean_bangumi_id)
            )
            if not subject:
                return None, f"未找到 Bangumi 条目 {clean_bangumi_id}"
            return subject, None

        if not clean_title:
            return None, "请先配置预览标题或 Bangumi ID"

        items = (
            self._cached_search(clean_title)
            if self._use_cache
            else await self._async_search_subjects(clean_title)
        )
        subject_brief = self._pick_best_subject(clean_title, items)
        if not subject_brief:
            return None, f"Bangumi 未搜索到 {clean_title}"

        subject_id = subject_brief.get("id")
        if not subject_id:
            return None, "命中条目缺少 Bangumi ID"

        subject = (
            self._cached_subject(str(subject_id))
            if self._use_cache
            else await self._async_fetch_subject_detail(str(subject_id))
        )
        if not subject:
            return None, f"无法获取 Bangumi 条目详情 {subject_id}"
        return subject, None

    def _build_preview_payload(
        self,
        title: Optional[str] = None,
        bangumi_id: Optional[str] = None,
        hanime_id: Optional[str] = None,
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """
        构造预览结果

        :param title (str): 查询标题
        :param bangumi_id (str): Bangumi ID

        :return Tuple: 预览结果与错误信息
        """
        subject: Optional[dict] = None
        hanime: Optional[Dict[str, Any]] = None

        source_count = 0
        bangumi_meta: Optional[Dict[str, Any]] = None
        hanime_meta: Optional[Dict[str, Any]] = None

        clean_hanime_id = self._extract_hanime_watch_id(hanime_id)
        if clean_hanime_id:
            html = self._request_hanime_watch(clean_hanime_id)
            if html:
                hanime = self._parse_hanime_watch(clean_hanime_id, html)
                if hanime:
                    source_count += 1
                    hanime_meta = self._build_hanime_metadata(hanime)

        subject, error = self._resolve_subject(title=title, bangumi_id=bangumi_id)
        if subject:
            source_count += 1
            bangumi_meta = self._build_metadata(subject)
        elif not hanime_meta:
            return None, error

        merged_metadata = self._merge_metadata(bangumi_meta=bangumi_meta, hanime_meta=hanime_meta)

        payload = {
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "query": {
                "title": str(title or "").strip(),
                "bangumi_id": str(bangumi_id or "").strip(),
                "hanime_id": str(hanime_id or "").strip(),
            },
            "source_count": source_count,
            "metadata": merged_metadata,
            "sources": {
                "bangumi": bangumi_meta,
                "hanime": hanime_meta,
            },
        }
        return payload, None

    def refresh_preview(self) -> Dict[str, Any]:
        """
        刷新详情页预览

        :return Dict: 刷新结果
        """
        if not self._enabled:
            return {"ok": False, "message": "插件未启用"}

        payload, error = self._build_preview_payload(
            title=self._preview_title,
            bangumi_id=self._preview_bangumi_id,
            hanime_id=self._preview_hanime_id,
        )
        if error or not payload:
            self.save_data("last_error", error or "未知错误")
            return {"ok": False, "message": error or "刷新失败"}

        self.save_data("last_preview", payload)
        self.del_data("last_error")
        return {"ok": True, "message": "刷新成功", "data": payload}

    def query_metadata(
        self,
        title: str = "",
        bangumi_id: str = "",
        hanime_id: str = "",
        save_preview: bool = False,
    ) -> Dict[str, Any]:
        """
        查询 metadata

        :param title (str): 查询标题
        :param bangumi_id (str): Bangumi ID
        :param save_preview (bool): 是否保存为详情页预览

        :return Dict: 查询结果
        """
        if not self._enabled:
            return {"ok": False, "message": "插件未启用"}

        payload, error = self._build_preview_payload(
            title=title or self._preview_title,
            bangumi_id=bangumi_id or self._preview_bangumi_id,
            hanime_id=hanime_id or self._preview_hanime_id,
        )
        if error or not payload:
            return {"ok": False, "message": error or "查询失败"}

        if save_preview:
            self.save_data("last_preview", payload)
            self.del_data("last_error")
        return {"ok": True, "message": "查询成功", "data": payload}

    def query_hanime(self, id: str = "", url: str = "") -> Dict[str, Any]:
        """
        查询 Hanime 条目

        :param id (str): watch ID
        :param url (str): watch 链接

        :return Dict: 查询结果
        """
        if not self._enabled:
            return {"ok": False, "message": "插件未启用"}

        watch_id = self._extract_hanime_watch_id(id) or self._extract_hanime_watch_id(url)
        if not watch_id:
            return {"ok": False, "message": "缺少有效的 Hanime ID 或链接"}

        html = self._request_hanime_watch(watch_id)
        if not html:
            return {"ok": False, "message": "获取 Hanime 页面失败，可能触发安全验证或网络不可达"}

        try:
            parsed = self._parse_hanime_watch(watch_id, html)
            if not parsed:
                return {"ok": False, "message": "解析 Hanime 页面失败"}
            meta = self._build_hanime_metadata(parsed)
        except Exception as err:
            logger.error("欢乐汇聚解析 Hanime 失败: %s", err, exc_info=True)
            return {"ok": False, "message": "解析 Hanime 页面失败"}

        return {"ok": True, "message": "ok", "data": {"watch": parsed, "metadata": meta}}

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

        try:
            items = self._search_subjects(meta.name)
            medias = [MediaInfo(bangumi_info=item) for item in items]
            self._apply_season(medias, getattr(meta, "begin_season", None))
            return medias
        except Exception as err:
            logger.error("欢乐汇聚搜索 Bangumi 失败: %s", err, exc_info=True)
            return []

    async def _async_search_medias(self, meta: MetaBase) -> Optional[List[MediaInfo]]:
        """
        异步全局搜索媒体

        :param meta (MetaBase): 媒体元数据

        :return List: 媒体结果
        """
        if not self._enabled:
            return None
        if not meta or not getattr(meta, "name", None):
            return []

        try:
            items = await self._async_search_subjects(meta.name)
            medias = [MediaInfo(bangumi_info=item) for item in items]
            self._apply_season(medias, getattr(meta, "begin_season", None))
            return medias
        except Exception as err:
            logger.error("欢乐汇聚异步搜索 Bangumi 失败: %s", err, exc_info=True)
            return []

    def _scrape_metadata(self, meta: MetaBase) -> Optional[List[MediaInfo]]:
        """
        全局刮削元数据

        :param meta (MetaBase): 媒体元数据

        :return List: 刮削结果
        """
        if not self._enabled:
            return None

        details: List[MediaInfo] = []
        mediaid = getattr(meta, "mediaid", None) if meta else None
        begin_season = getattr(meta, "begin_season", None) if meta else None

        try:
            if mediaid:
                bangumi_id = str(mediaid).split(":", 1)[-1]
                detail = (
                    self._cached_subject(bangumi_id)
                    if self._use_cache
                    else self._fetch_subject_detail(bangumi_id)
                )
                if detail:
                    details.append(MediaInfo(bangumi_info=detail))
            else:
                medias = self._search_medias(meta) or []
                for media in medias:
                    bangumi_id = getattr(media, "bangumi_id", None)
                    if not bangumi_id:
                        continue
                    detail = (
                        self._cached_subject(str(bangumi_id))
                        if self._use_cache
                        else self._fetch_subject_detail(str(bangumi_id))
                    )
                    if detail:
                        details.append(MediaInfo(bangumi_info=detail))
            self._apply_season(details, begin_season)
            return details
        except Exception as err:
            logger.error("欢乐汇聚刮削 Bangumi 元数据失败: %s", err, exc_info=True)
            return []

    async def _async_scrape_metadata(self, meta: MetaBase) -> Optional[List[MediaInfo]]:
        """
        异步全局刮削元数据

        :param meta (MetaBase): 媒体元数据

        :return List: 刮削结果
        """
        if not self._enabled:
            return None

        details: List[MediaInfo] = []
        mediaid = getattr(meta, "mediaid", None) if meta else None
        begin_season = getattr(meta, "begin_season", None) if meta else None

        try:
            if mediaid:
                bangumi_id = str(mediaid).split(":", 1)[-1]
                detail = (
                    self._cached_subject(bangumi_id)
                    if self._use_cache
                    else await self._async_fetch_subject_detail(bangumi_id)
                )
                if detail:
                    details.append(MediaInfo(bangumi_info=detail))
            else:
                medias = await self._async_search_medias(meta) or []
                for media in medias:
                    bangumi_id = getattr(media, "bangumi_id", None)
                    if not bangumi_id:
                        continue
                    detail = (
                        self._cached_subject(str(bangumi_id))
                        if self._use_cache
                        else await self._async_fetch_subject_detail(str(bangumi_id))
                    )
                    if detail:
                        details.append(MediaInfo(bangumi_info=detail))
            self._apply_season(details, begin_season)
            return details
        except Exception as err:
            logger.error("欢乐汇聚异步刮削 Bangumi 元数据失败: %s", err, exc_info=True)
            return []

    def _bangumi_info(self, bangumiid: int) -> Optional[MediaInfo]:
        """
        根据 Bangumi ID 获取媒体详情

        :param bangumiid (int): Bangumi ID

        :return MediaInfo: 媒体信息
        """
        if not self._enabled or not bangumiid:
            return None
        try:
            detail = (
                self._cached_subject(str(bangumiid))
                if self._use_cache
                else self._fetch_subject_detail(str(bangumiid))
            )
            return MediaInfo(bangumi_info=detail) if isinstance(detail, dict) else None
        except Exception as err:
            logger.error("欢乐汇聚获取 Bangumi 详情失败: %s", err, exc_info=True)
            return None

    async def _async_bangumi_info(self, bangumiid: int) -> Optional[MediaInfo]:
        """
        异步根据 Bangumi ID 获取媒体详情

        :param bangumiid (int): Bangumi ID

        :return MediaInfo: 媒体信息
        """
        if not self._enabled or not bangumiid:
            return None
        try:
            detail = (
                self._cached_subject(str(bangumiid))
                if self._use_cache
                else await self._async_fetch_subject_detail(str(bangumiid))
            )
            return MediaInfo(bangumi_info=detail) if isinstance(detail, dict) else None
        except Exception as err:
            logger.error("欢乐汇聚异步获取 Bangumi 详情失败: %s", err, exc_info=True)
            return None

    def _recognize_media(self, bangumiid: int = None, **kwargs) -> Optional[MediaInfo]:
        """
        根据 Bangumi ID 识别媒体

        :param bangumiid (int): Bangumi ID

        :return MediaInfo: 媒体信息
        """
        if not self._enabled:
            return None
        if bangumiid:
            return self._bangumi_info(bangumiid)

        watch_id = self._extract_hanime_watch_id_from_kwargs(kwargs)
        if watch_id:
            html = self._request_hanime_watch(watch_id)
            if html:
                parsed = self._parse_hanime_watch(watch_id, html)
                if parsed:
                    query_title = str(parsed.get("series") or parsed.get("title") or "").strip()
                    if query_title:
                        items = (
                            self._cached_search(query_title)
                            if self._use_cache
                            else self._search_subjects(query_title)
                        )
                        best = self._pick_best_subject(query_title, items)
                        if best and best.get("id"):
                            return self._bangumi_info(int(best.get("id")))

        title = self._extract_title_from_kwargs(kwargs)
        if not title:
            return None
        items = self._cached_search(title) if self._use_cache else self._search_subjects(title)
        best = self._pick_best_subject(title, items)
        if not best or not best.get("id"):
            logger.info("欢乐汇聚未识别到 Bangumi: %s", title)
            return None
        return self._bangumi_info(int(best.get("id")))

    async def _async_recognize_media(
        self, bangumiid: int = None, **kwargs
    ) -> Optional[MediaInfo]:
        """
        异步根据 Bangumi ID 识别媒体

        :param bangumiid (int): Bangumi ID

        :return MediaInfo: 媒体信息
        """
        if not self._enabled:
            return None
        if bangumiid:
            return await self._async_bangumi_info(bangumiid)

        watch_id = self._extract_hanime_watch_id_from_kwargs(kwargs)
        if watch_id:
            html = self._request_hanime_watch(watch_id)
            if html:
                parsed = self._parse_hanime_watch(watch_id, html)
                if parsed:
                    query_title = str(parsed.get("series") or parsed.get("title") or "").strip()
                    if query_title:
                        items = (
                            self._cached_search(query_title)
                            if self._use_cache
                            else await self._async_search_subjects(query_title)
                        )
                        best = self._pick_best_subject(query_title, items)
                        if best and best.get("id"):
                            return await self._async_bangumi_info(int(best.get("id")))

        title = self._extract_title_from_kwargs(kwargs)
        if not title:
            return None
        items = (
            self._cached_search(title)
            if self._use_cache
            else await self._async_search_subjects(title)
        )
        best = self._pick_best_subject(title, items)
        if not best or not best.get("id"):
            logger.info("欢乐汇聚未识别到 Bangumi: %s", title)
            return None
        return await self._async_bangumi_info(int(best.get("id")))
