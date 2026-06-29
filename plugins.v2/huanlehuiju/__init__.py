from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

from app.core.cache import cached
from app.core.config import settings
from app.log import logger
from app.plugins import _PluginBase
from app.utils.http import RequestUtils


class HuanLeHuiju(_PluginBase):
    """
    欢乐汇聚插件

    第一版聚焦 Bangumi 数据源，提供 metadata 预览、融合展示与手动刷新能力
    后续可在相同数据结构下继续接入 TMDB、豆瓣等来源
    """

    plugin_name = "欢乐汇聚"
    plugin_desc = "MoviePilot 详情页 metadata 融合预览插件，第一版接入 Bangumi"
    plugin_order = 99
    plugin_version = "1.0.0"
    plugin_author = "踏马奔腾"
    author_url = "https://trae.ai"
    plugin_icon = (
        "https://raw.githubusercontent.com/jxxghp/MoviePilot-Plugins/main/icons/bangumi.png"
    )

    _enabled: bool = False
    _authorization: str = ""
    _preview_title: str = ""
    _preview_bangumi_id: str = ""
    _use_cache: bool = True
    _prefer_exact_match: bool = True

    def init_plugin(self, config: dict = None) -> None:
        """
        生效插件配置

        :param config (dict): 插件配置
        """
        self._enabled = False
        self._authorization = ""
        self._preview_title = ""
        self._preview_bangumi_id = ""
        self._use_cache = True
        self._prefer_exact_match = True

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
        self._use_cache = bool(config.get("use_cache", True))
        self._prefer_exact_match = bool(config.get("prefer_exact_match", True))

    def get_state(self) -> bool:
        """
        获取插件状态

        :return bool: 插件是否启用
        """
        return self._enabled

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
                "auth": "apikey",
                "summary": "刷新欢乐汇聚预览",
                "description": "按当前插件配置刷新 Bangumi metadata 预览结果",
            },
            {
                "path": "/query_metadata",
                "endpoint": self.query_metadata,
                "methods": ["GET"],
                "auth": "apikey",
                "summary": "查询融合 metadata",
                "description": "按标题或 Bangumi ID 查询 metadata，并可选保存为详情页预览",
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
                        "component": "VAlert",
                        "props": {
                            "type": "info",
                            "variant": "tonal",
                            "text": "第一版只接入 Bangumi，用于验证 metadata 融合结构与详情展示，后续可扩展 TMDB、豆瓣等来源",
                        },
                    },
                ],
            }
        ], {
            "enabled": False,
            "authorization": "",
            "preview_title": "",
            "preview_bangumi_id": "",
            "use_cache": True,
            "prefer_exact_match": True,
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
                                        "api": "plugin/HuanLeHuiju/refresh_preview",
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
                        "text": "暂无预览数据，请先在插件配置中填写标题或 Bangumi ID，然后点击刷新预览",
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
                        "text": f"查询条件：标题={query.get('title') or '未填写'} / Bangumi ID={query.get('bangumi_id') or '未填写'}",
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

    def _fetch_subject_detail(self, bangumi_id: str) -> Optional[dict]:
        """
        获取 Bangumi 条目详情

        :param bangumi_id (str): Bangumi ID

        :return dict: 条目详情
        """
        return self._request_json(f"https://api.bgm.tv/v0/subjects/{bangumi_id}")

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

    def _build_preview_payload(
        self,
        title: Optional[str] = None,
        bangumi_id: Optional[str] = None,
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """
        构造预览结果

        :param title (str): 查询标题
        :param bangumi_id (str): Bangumi ID

        :return Tuple: 预览结果与错误信息
        """
        subject, error = self._resolve_subject(title=title, bangumi_id=bangumi_id)
        if error or not subject:
            return None, error

        payload = {
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "query": {
                "title": str(title or "").strip(),
                "bangumi_id": str(bangumi_id or "").strip(),
            },
            "source_count": 1,
            "metadata": self._build_metadata(subject),
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
        )
        if error or not payload:
            return {"ok": False, "message": error or "查询失败"}

        if save_preview:
            self.save_data("last_preview", payload)
            self.del_data("last_error")
        return {"ok": True, "message": "查询成功", "data": payload}
