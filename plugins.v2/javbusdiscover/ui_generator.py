from typing import Dict, List


CATEGORY_OPTIONS = [
    {"Value": "有码", "Text": "有码"},
    {"Value": "无码", "Text": "无码"},
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


def javbus_filter_ui() -> List[dict]:
    """
    JavBus 过滤参数 UI 配置

    :return List: 前端筛选 UI 列表
    """
    return [
        _build_chip_row("category", "类别", CATEGORY_OPTIONS),
    ]

