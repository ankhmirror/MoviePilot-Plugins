from typing import Any, Dict, List, Tuple, Optional

from app.plugins import _PluginBase
from app.core.config import settings
from app.core.event import eventmanager, Event
from app.core.cache import cached
from app.log import logger
from app.schemas import DiscoverSourceEventData
from app.schemas.types import ChainEventType
from app.utils.http import RequestUtils
from app import schemas


JAVBUS_URL = "https://www.javbus.com/"
JAVBUS_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Referer": "https://www.javbus.com/",
}


class JavBusDiscover(_PluginBase):
    plugin_name = "JavBus探索"
    plugin_desc = "在探索中增加 JavBus 标签页，浏览站点内容"
    plugin_icon = "JavBus.png"
    plugin_version = "1.0.0"
    plugin_author = "DDSRem"
    author_url = "https://www.javbus.com/"
    plugin_config_prefix = "javbusdiscover_"
    plugin_order = 99
    auth_level = 1

    _enabled: bool = False

    def init_plugin(self, config: dict = None):
        if config:
            self._enabled = bool(config.get("enabled", False))

    def get_state(self) -> bool:
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        return []

    def get_api(self) -> List[Dict[str, Any]]:
        return [
            {
                "path": "/javbus_discover",
                "endpoint": self.javbus_discover,
                "methods": ["GET"],
                "summary": "JavBus 探索数据源",
                "description": "获取 JavBus 首页内容并转换为探索媒体信息",
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

    def stop_service(self):
        pass

    @staticmethod
    def _fetch_javbus_home() -> Optional[str]:
        try:
            res = RequestUtils(headers=JAVBUS_HEADERS).get_res(JAVBUS_URL)
            if res is None:
                logger.error("无法连接 JavBus，请检查网络连接")
                return None
            if not res.ok:
                logger.error(f"请求 JavBus 失败：{res.text}")
                return None
            return res.text
        except Exception as e:
            logger.error(f"请求 JavBus 时发生异常: {str(e)}")
            return None

    @staticmethod
    def _parse_javbus_home(html: str) -> List[schemas.MediaInfo]:
        import re

        items: List[schemas.MediaInfo] = []
        pattern = re.compile(r'<a href="(?P<href>[^"]+)"\s+class="movie-box">[\s\S]*?<img\s+src="(?P<img>[^"]+)"[\s\S]*?alt="(?P<alt>[^"]+)"', re.IGNORECASE)
        for m in pattern.finditer(html or ""):
            href = m.group("href")
            img = m.group("img")
            title = m.group("alt")
            media_id = href.rstrip("/").split("/")[-1]
            items.append(
                schemas.MediaInfo(
                    type="电影",
                    source="javbus",
                    title=title,
                    mediaid_prefix="javbus",
                    media_id=media_id,
                    poster_path=img,
                    vote_average=0,
                    first_air_date="",
                )
            )
        return items

    @cached(region="javbus_discover", ttl=1800, skip_none=True)
    def _get_javbus_items(self) -> Optional[List[schemas.MediaInfo]]:
        html = self._fetch_javbus_home()
        if not html:
            return None
        return self._parse_javbus_home(html)

    def javbus_discover(self, page: int = 1, count: int = 20) -> List[schemas.MediaInfo]:
        try:
            items = self._get_javbus_items() or []
            start_idx = (page - 1) * count
            end_idx = start_idx + count
            return items[start_idx:end_idx]
        except Exception as e:
            logger.error(f"获取 JavBus 数据失败: {str(e)}", exc_info=True)
            return []

    @eventmanager.register(ChainEventType.DiscoverSource)
    def discover_source(self, event: Event):
        if not self._enabled:
            return
        event_data: DiscoverSourceEventData = event.event_data
        source = schemas.DiscoverMediaSource(
            name="JavBus",
            mediaid_prefix="javbus",
            api_path=f"plugin/JavBusDiscover/javbus_discover?apikey={settings.API_TOKEN}",
            filter_params={},
            filter_ui=[],
        )
        if event_data.extra_sources is None:
            event_data.extra_sources = [source]
        else:
            event_data.extra_sources.append(source)