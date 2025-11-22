from typing import Any, Dict, List, Tuple, Optional
 

from app.core.config import settings
from app.plugins import _PluginBase
from app.utils.http import RequestUtils, AsyncRequestUtils
from app.core.meta import MetaBase
from app.core.context import MediaInfo
 


class BangumiAuthorization(_PluginBase):
    """
    Bangumi 授权插件类
    
    为 MoviePilot 添加 Bangumi API 授权功能，允许用户使用自定义的 Authorization 令牌访问 Bangumi API，
    从而获取更高级的访问权限和更多的媒体信息。
    """
    
    # 插件基本信息
    plugin_name = "BangumiAuthorization"          # 插件名称
    plugin_desc = "为 Bangumi 搜索附加 Authorization"  # 插件描述
    plugin_order = 99                           # 插件加载顺序
    plugin_version = "1.1.0"                    # 插件版本
    plugin_author = "踏马奔腾"                     # 插件作者
    plugin_icon = "https://raw.githubusercontent.com/jxxghp/MoviePilot-Plugins/main/icons/bangumi.png"  # 插件图标

    # 插件配置参数
    _enabled: bool = False        # 插件是否启用
    _authorization: str = ""     # Bangumi Authorization 令牌

    def _headers(self) -> Dict[str, str]:
        """
        生成请求头信息
        
        为 Bangumi API 请求生成带有 Authorization 的请求头，确保请求格式正确。
        如果用户提供的授权令牌不以 "bearer " 开头，则自动添加前缀。
        
        Returns:
            Dict[str, str]: 包含 Authorization 的请求头字典
        """
        headers: Dict[str, str] = {"Accept": "application/json"}
        if self._authorization:
            auth = self._authorization.strip()
            headers["Authorization"] = auth if auth.lower().startswith("bearer ") else f"Bearer {auth}"
        return headers

    def init_plugin(self, config: dict = None):
        """
        初始化插件配置
        
        从配置字典中读取插件的启用状态和授权令牌，设置到插件实例中。
        
        Args:
            config (dict, optional): 包含插件配置的字典，默认为 None
        """
        if config:
            self._enabled = bool(config.get("enabled", False))
            auth = str(config.get("authorization", "") or "").strip()
            if auth:
                self._authorization = auth if auth.lower().startswith("bearer ") else f"Bearer {auth}"
            else:
                self._authorization = ""

    def _season_text(self, season: Optional[int]) -> Optional[str]:
        if not season:
            return None
        try:
            import cn2an
            return cn2an.an2cn(season, "low")
        except Exception:
            return None

    def _apply_season(self, medias: List[MediaInfo], begin_season: Optional[int]):
        if not begin_season or not medias:
            return
        season_str = self._season_text(begin_season)
        for m in medias:
            if m.type and m.type.value == "电视剧":
                if season_str:
                    m.title = f"{m.title} 第{season_str}季"
                m.season = begin_season

    def get_state(self) -> bool:
        """
        获取插件当前状态
        
        Returns:
            bool: 插件是否已启用
        """
        return self._enabled

    def get_api(self) -> List[Dict[str, Any]]:
        """
        获取插件提供的API接口
        
        定义插件暴露给系统的API接口列表，这些接口可以通过HTTP请求访问。
        
        Returns:
            List[Dict[str, Any]]: API接口配置列表
        """
        return [
            {
                "path": "/refresh_bangumi",          # API接口路径
                "endpoint": self._refresh_bangumi,    # 处理函数
                "methods": ["GET"],                   # 请求方法
                "auth": "apikey",                     # 认证方式
                "summary": "刷新 Bangumi 授权配置",       # 接口摘要
                "description": "重新加载并生效插件配置",    # 接口详细描述
            }
        ]

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        """
        获取插件配置表单
        
        定义插件在管理界面中显示的配置表单，包括启用开关和授权令牌输入框。
        
        Returns:
            Tuple[List[dict], Dict[str, Any]]: 表单配置列表和默认配置值
        """
        return [
            {
                "component": "VForm",  # 表单组件
                "content": [
                    {
                        "component": "VRow",  # 行组件
                        "content": [
                            {
                                "component": "VCol",  # 列组件，占用4/12的md屏幕宽度
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VSwitch",  # 开关组件，控制插件启用状态
                                        "props": {"model": "enabled", "label": "启用插件"},
                                    }
                                ],
                            },
                            {
                                "component": "VCol",  # 列组件，占用8/12的md屏幕宽度
                                "props": {"cols": 12, "md": 8},
                                "content": [
                                    {
                                        "component": "VTextField",  # 文本输入框，用于输入授权令牌
                                        "props": {
                                            "model": "authorization",  # 绑定的配置字段
                                            "label": "Bangumi Authorization",  # 输入框标签
                                            "clearable": True,  # 可清空功能
                                        },
                                    }
                                ],
                            },
                        ],
                    }
                ],
            }
        ], {"enabled": False, "authorization": ""}  # 默认配置值

    def get_page(self) -> List[dict]:
        """
        获取插件自定义页面
        
        定义插件在管理界面中显示的自定义页面内容，包括提示信息和创建令牌的链接按钮。
        
        Returns:
            List[dict]: 页面组件配置列表
        """
        return [
            {
                "component": "VRow",  # 行组件
                "content": [
                    {
                        "component": "VCol",  # 列组件，占满整行
                        "props": {"cols": 12},
                        "content": [
                            {
                                "component": "VAlert",  # 提示框组件
                                "props": {
                                    "type": "info",  # 信息类型提示
                                    "variant": "tonal",  # 柔和样式变体
                                    "text": "需要创建 Bangumi Authorization 令牌"  # 提示文本
                                }
                            }
                        ]
                    },
                    {
                        "component": "VCol",  # 列组件，占满整行
                        "props": {"cols": 12},
                        "content": [
                            {
                                "component": "VBtn",  # 按钮组件
                                "props": {
                                    "href": "https://next.bgm.tv/demo/access-token/create",  # 跳转到创建令牌页面
                                    "target": "_blank",  # 在新窗口打开
                                    "rel": "noopener",  # 安全设置
                                    "color": "primary"  # 主色调
                                },
                                "text": "前往创建令牌"  # 按钮文本
                            }
                        ]
                    }
                ]
            }
        ]

    def get_module(self) -> Dict[str, Any]:
        """
        获取插件模块映射
        
        定义插件提供给系统的各个功能模块，每个模块对应一个处理函数。
        
        Returns:
            Dict[str, Any]: 模块名称到处理函数的映射
        """
        return {
            "search_medias": self._search_medias,             # 同步媒体搜索方法
            "async_search_medias": self._async_search_medias,  # 异步媒体搜索方法
            "scrape_metadata": self._scrape_metadata,          # 同步元数据抓取方法
            "async_scrape_metadata": self._async_scrape_metadata,  # 异步元数据抓取方法
            "bangumi_info": self._bangumi_info,               # 同步获取Bangumi信息方法
            "async_bangumi_info": self._async_bangumi_info,    # 异步获取Bangumi信息方法
            "recognize_media": self._recognize_media,          # 同步媒体识别方法
            "async_recognize_media": self._async_recognize_media,  # 异步媒体识别方法
        }

    def stop_service(self):
        """
        停止插件服务
        
        插件停止时调用的方法，本插件不需要特殊的停止逻辑。
        """
        pass

    def _search_medias(self, meta: MetaBase) -> Optional[List[MediaInfo]]:
        """
        同步搜索媒体信息
        
        根据提供的元数据信息，从 Bangumi API 搜索相关的媒体内容，并返回匹配的媒体信息列表。
        支持添加季度信息，对电视剧类型的媒体自动设置季度标题和编号。
        
        Args:
            meta (MetaBase): 媒体元数据对象，包含搜索关键词和可能的季度信息
            
        Returns:
            Optional[List[MediaInfo]]: 匹配的媒体信息列表，如果插件未启用则返回 None
        """
        # 检查插件是否启用
        if not self._enabled:
            return None
        # 验证输入参数
        if not meta or not meta.name:
            return []
        
        # 构建搜索URL并发送请求
        url = f"https://api.bgm.tv/search/subject/{meta.name}"
        req = RequestUtils(ua=settings.NORMAL_USER_AGENT, headers=self._headers())
        resp = req.get_res(url)
        
        # 处理响应结果
        if not resp:
            return []
        try:
            data = resp.json()
        except Exception:
            return []
        
        # 提取媒体列表并转换为MediaInfo对象
        items = data.get("list") or []
        medias = [MediaInfo(bangumi_info=info) for info in items]
        
        self._apply_season(medias, getattr(meta, "begin_season", None))
        
        return medias

    def _scrape_metadata(self, meta: MetaBase) -> Optional[List[MediaInfo]]:
        """
        同步抓取媒体元数据
        
        根据提供的元数据信息，从 Bangumi API 获取详细的媒体元数据信息。
        支持两种模式：
        1. 如果提供了 mediaid，则直接获取指定 ID 的媒体详情
        2. 如果没有提供 mediaid，则先搜索再获取每个结果的详细信息
        
        Args:
            meta (MetaBase): 媒体元数据对象，包含搜索关键词、可能的 mediaid 和季度信息
            
        Returns:
            Optional[List[MediaInfo]]: 媒体详细信息列表，如果插件未启用则返回 None
        """
        # 检查插件是否启用
        if not self._enabled:
            return None
        
        # 初始化请求工具和结果列表
        req = RequestUtils(ua=settings.NORMAL_USER_AGENT, headers=self._headers())
        details: List[MediaInfo] = []
        
        # 尝试获取 mediaid
        mediaid = getattr(meta, "mediaid", None)
        
        if mediaid:
            # 模式1：直接通过 mediaid 获取详细信息
            try:
                # 提取 Bangumi 主题 ID
                sid = str(mediaid).split(":", 1)[-1]
                # 请求详细信息
                dresp = req.get_res(f"https://api.bgm.tv/subject/{sid}")
                if dresp:
                    dinfo = dresp.json()
                    details.append(MediaInfo(bangumi_info=dinfo))
            except Exception:
                return []
        else:
            # 模式2：先搜索再获取详细信息
            if not meta or not meta.name:
                return []
            
            # 搜索相关媒体
            url = f"https://api.bgm.tv/search/subject/{meta.name}"
            resp = req.get_res(url)
            if not resp:
                return []
            
            try:
                data = resp.json()
            except Exception:
                return []
            
            # 为每个搜索结果获取详细信息
            items = data.get("list") or []
            for info in items:
                sid = (info or {}).get("id")
                if not sid:
                    continue
                
                # 请求单个媒体的详细信息
                dresp = req.get_res(f"https://api.bgm.tv/subject/{sid}")
                if not dresp:
                    continue
                
                try:
                    dinfo = dresp.json()
                    details.append(MediaInfo(bangumi_info=dinfo))
                except Exception:
                    continue
        
        self._apply_season(details, getattr(meta, "begin_season", None))
        
        return details

    async def _async_search_medias(self, meta: MetaBase) -> Optional[List[MediaInfo]]:
        """
        异步搜索媒体信息
        
        根据提供的元数据信息，以异步方式从 Bangumi API 搜索相关的媒体内容，返回匹配的媒体信息列表。
        这是 _search_medias 方法的异步版本，功能相同但使用异步请求。
        
        Args:
            meta (MetaBase): 媒体元数据对象，包含搜索关键词和可能的季度信息
            
        Returns:
            Optional[List[MediaInfo]]: 匹配的媒体信息列表，如果插件未启用则返回 None
        """
        # 检查插件是否启用
        if not self._enabled:
            return None
        # 验证输入参数
        if not meta or not meta.name:
            return []
        
        # 构建搜索URL并发送异步请求
        url = f"https://api.bgm.tv/search/subject/{meta.name}"
        req = AsyncRequestUtils(ua=settings.NORMAL_USER_AGENT, headers=self._headers())
        resp = await req.get_res(url)
        
        # 处理响应结果
        if not resp:
            return []
        try:
            data = resp.json()
        except Exception:
            return []
        
        # 提取媒体列表并转换为MediaInfo对象
        items = data.get("list") or []
        medias = [MediaInfo(bangumi_info=info) for info in items]
        
        self._apply_season(medias, getattr(meta, "begin_season", None))
        
        return medias

    async def _async_scrape_metadata(self, meta: MetaBase) -> Optional[List[MediaInfo]]:
        """
        异步抓取媒体元数据
        
        根据提供的元数据信息，以异步方式从 Bangumi API 获取详细的媒体元数据信息。
        这是 _scrape_metadata 方法的异步版本，功能相同但使用异步请求。
        
        Args:
            meta (MetaBase): 媒体元数据对象，包含搜索关键词、可能的 mediaid 和季度信息
            
        Returns:
            Optional[List[MediaInfo]]: 媒体详细信息列表，如果插件未启用则返回 None
        """
        # 检查插件是否启用
        if not self._enabled:
            return None
        
        # 初始化异步请求工具和结果列表
        req = AsyncRequestUtils(ua=settings.NORMAL_USER_AGENT, headers=self._headers())
        details: List[MediaInfo] = []
        
        # 尝试获取 mediaid
        mediaid = getattr(meta, "mediaid", None)
        
        if mediaid:
            # 模式1：直接通过 mediaid 获取详细信息
            try:
                # 提取 Bangumi 主题 ID
                sid = str(mediaid).split(":", 1)[-1]
                # 发送异步请求获取详细信息
                dresp = await req.get_res(f"https://api.bgm.tv/subject/{sid}")
                if dresp:
                    dinfo = dresp.json()
                    details.append(MediaInfo(bangumi_info=dinfo))
            except Exception:
                return []
        else:
            # 模式2：先搜索再获取详细信息
            if not meta or not meta.name:
                return []
            
            # 发送异步搜索请求
            url = f"https://api.bgm.tv/search/subject/{meta.name}"
            resp = await req.get_res(url)
            if not resp:
                return []
            
            try:
                data = resp.json()
            except Exception:
                return []
            
            # 为每个搜索结果获取详细信息
            items = data.get("list") or []
            for info in items:
                sid = (info or {}).get("id")
                if not sid:
                    continue
                
                # 发送异步请求获取单个媒体的详细信息
                dresp = await req.get_res(f"https://api.bgm.tv/subject/{sid}")
                if not dresp:
                    continue
                
                try:
                    dinfo = dresp.json()
                    details.append(MediaInfo(bangumi_info=dinfo))
                except Exception:
                    continue
        
        self._apply_season(details, getattr(meta, "begin_season", None))
        
        return details

    def _recognize_media(self, bangumiid: int = None, **kwargs) -> Optional[MediaInfo]:
        """
        根据Bangumi ID识别媒体信息
        
        使用Bangumi ID识别并获取对应的媒体详细信息。
        这是一个同步方法，内部调用 _bangumi_info 获取详细数据。
        
        Args:
            bangumiid (int, optional): Bangumi 主题 ID
            **kwargs: 额外参数（保留接口兼容性）
            
        Returns:
            Optional[MediaInfo]: 媒体信息对象，如果插件未启用或ID无效则返回 None
        """
        # 检查插件是否启用
        if not self._enabled:
            return None
        # 验证ID参数
        if not bangumiid:
            return None
        # 调用 _bangumi_info 获取详细信息
        info = self._bangumi_info(bangumiid)
        # 验证返回结果类型
        if isinstance(info, MediaInfo):
            return info
        return None

    async def _async_recognize_media(self, bangumiid: int = None, **kwargs) -> Optional[MediaInfo]:
        """
        异步根据Bangumi ID识别媒体信息
        
        使用Bangumi ID异步识别并获取对应的媒体详细信息。
        这是一个异步方法，内部调用 _async_bangumi_info 获取详细数据。
        
        Args:
            bangumiid (int, optional): Bangumi 主题 ID
            **kwargs: 额外参数（保留接口兼容性）
            
        Returns:
            Optional[MediaInfo]: 媒体信息对象，如果插件未启用或ID无效则返回 None
        """
        # 检查插件是否启用
        if not self._enabled:
            return None
        # 验证ID参数
        if not bangumiid:
            return None
        # 异步调用 _async_bangumi_info 获取详细信息
        info = await self._async_bangumi_info(bangumiid)
        # 验证返回结果类型
        if isinstance(info, MediaInfo):
            return info
        return None

    def _bangumi_info(self, bangumiid: int) -> Optional[MediaInfo]:
        """
        获取Bangumi媒体详细信息
        
        根据提供的Bangumi ID，从Bangumi API v0获取详细的媒体信息。
        使用同步HTTP请求方式获取数据。
        
        Args:
            bangumiid (int): Bangumi 主题 ID
            
        Returns:
            Optional[MediaInfo]: 媒体信息对象，如果插件未启用、ID无效或请求失败则返回 None
        """
        # 检查插件是否启用
        if not self._enabled:
            return None
        # 验证ID参数
        if not bangumiid:
            return None
        # 初始化请求工具
        req = RequestUtils(ua=settings.NORMAL_USER_AGENT, headers=self._headers())
        # 发送同步请求获取数据
        resp = req.get_res(
            f"https://api.bgm.tv/v0/subjects/{bangumiid}"
        )
        data = None
        # 检查响应状态并解析JSON
        if resp and resp.status_code == 200:
            try:
                data = resp.json()
            except Exception:
                data = None
        # 返回媒体信息对象或None
        return MediaInfo(bangumi_info=data) if isinstance(data, dict) else None

    async def _async_bangumi_info(self, bangumiid: int) -> Optional[MediaInfo]:
        """
        异步获取Bangumi媒体详细信息
        
        根据提供的Bangumi ID，从Bangumi API v0异步获取详细的媒体信息。
        使用异步HTTP请求方式获取数据。
        
        Args:
            bangumiid (int): Bangumi 主题 ID
            
        Returns:
            Optional[MediaInfo]: 媒体信息对象，如果插件未启用、ID无效或请求失败则返回 None
        """
        # 检查插件是否启用
        if not self._enabled:
            return None
        # 验证ID参数
        if not bangumiid:
            return None
        # 初始化异步请求工具
        req = AsyncRequestUtils(ua=settings.NORMAL_USER_AGENT, headers=self._headers())
        # 发送异步请求获取数据
        resp = await req.get_res(
            f"https://api.bgm.tv/v0/subjects/{bangumiid}"
        )
        data = None
        # 检查响应状态并解析JSON
        if resp and resp.status_code == 200:
            try:
                data = resp.json()
            except Exception:
                data = None
        # 返回媒体信息对象或None
        return MediaInfo(bangumi_info=data) if isinstance(data, dict) else None

    def _refresh_bangumi(self, **kwargs) -> Dict[str, Any]:
        """
        刷新Bangumi授权配置
        
        重新从配置存储中加载插件配置并初始化，用于在配置更改后刷新插件状态。
        
        Args:
            **kwargs: 额外参数（保留接口兼容性）
            
        Returns:
            Dict[str, Any]: 操作结果字典，包含:
                - ok (bool): 操作是否成功
                - enabled (bool): 插件是否启用（仅在操作成功时返回）
        """
        # 获取最新的配置，如果不存在则使用默认配置
        cfg = self.get_config(self.__class__.__name__) or {"enabled": False, "authorization": ""}
        try:
            # 使用新配置重新初始化插件
            self.init_plugin(cfg)
            # 返回成功结果和当前启用状态
            return {"ok": True, "enabled": self._enabled}
        except Exception:
            # 发生异常时返回失败结果
            return {"ok": False}