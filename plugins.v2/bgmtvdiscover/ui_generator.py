from typing import Dict, List


TAG_OPTIONS = [
    {"Value": "里番", "Text": "里番"},
    {"Value": "R-18", "Text": "R18"},
    {"Value": "泡面番", "Text": "泡面番"},
    {"Value": "后宫", "Text": "后宫"},
]

SORT_OPTIONS = [
    {"Value": "rank", "Text": "排名"},
    {"Value": "date", "Text": "日期"},
    {"Value": "score", "Text": "评分"},
    {"Value": "collects", "Text": "收藏"},
]


def _build_chip_row(
    model: str, label: str, options: List[Dict[str, str]]
) -> Dict[str, object]:
    """
    构造一行筛选 UI

    :param model (str): 绑定字段名
    :param label (str): 筛选标签
    :param options (List): 筛选项列表

    :return Dict: 单行筛选 UI 配置
    """
    return {
        "component": "div",
        "props": {"class": "flex justify-start items-center"},
        "content": [
            {
                "component": "div",
                "props": {"class": "mr-5"},
                "content": [{"component": "VLabel", "text": label}],
            },
            {
                "component": "VChipGroup",
                "props": {"model": model},
                "content": [
                    {
                        "component": "VChip",
                        "props": {
                            "filter": True,
                            "tile": True,
                            "value": item["Value"],
                        },
                        "text": item["Text"],
                    }
                    for item in options
                ],
            },
        ],
    }


def bgm_filter_ui() -> List[dict]:
    """
    Bangumi 标签探索过滤参数 UI 配置

    :return List: 前端筛选 UI 列表
    """
    return [
        _build_chip_row("tag", "标签", TAG_OPTIONS),
        _build_chip_row("sort", "排序", SORT_OPTIONS),
    ]

