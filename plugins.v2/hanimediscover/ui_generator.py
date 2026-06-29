from datetime import datetime
from typing import Dict, List


GENRE_OPTIONS = [
    {"Value": "裏番", "Text": "里番"},
    {"Value": "泡麵番", "Text": "泡面番"},
    {"Value": "Motion Anime", "Text": "Motion Anime"},
    {"Value": "3DCG", "Text": "3DCG"},
    {"Value": "2.5D", "Text": "2.5D"},
    {"Value": "2D動畫", "Text": "2D动画"},
    {"Value": "AI生成", "Text": "AI生成"},
    {"Value": "MMD", "Text": "MMD"},
    {"Value": "Cosplay", "Text": "Cosplay"},
]

SORT_OPTIONS = [
    {"Value": "本日排行", "Text": "排名"},
    {"Value": "最新上傳", "Text": "日期"},
]


def _build_year_options() -> List[Dict[str, str]]:
    """
    构造年份筛选项

    :return List: 年份筛选项
    """
    current_year = datetime.now().year
    return [
        {"Value": f"{year} 年", "Text": str(year)}
        for year in range(current_year, 1989, -1)
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


def hanime_filter_ui() -> List[dict]:
    """
    Hanime 过滤参数 UI 配置

    :return List: 前端筛选 UI 列表
    """
    return [
        _build_chip_row("genre", "类别", GENRE_OPTIONS),
        _build_chip_row("sort", "排序", SORT_OPTIONS),
        _build_chip_row("date", "年份", _build_year_options()),
    ]
