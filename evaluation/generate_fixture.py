"""Generate a fixed-seed 10,000-row synthetic Chinese review fixture.

Usage:
    python -m evaluation.generate_fixture \
        --rows 10000 --output evaluation/fixtures/synthetic_10000.csv
"""

from __future__ import annotations

import argparse
import random
from pathlib import Path

import pandas as pd

PACKAGE_DIR = Path(__file__).resolve().parent

NEGATIVE_TEMPLATES = [
    "无故封号，申诉没人理",
    "客服完全联系不上，太失望了",
    "广告越来越多，推荐质量下降",
    "评论区被水军刷屏",
    "更新后经常闪退，体验很差",
    "笔记被限流，流量骤降",
    "账号莫名被禁言，没有任何通知",
    "搜索功能越来越难用",
    "隐私设置形同虚设",
    "内容审核乱封号，误伤严重",
]

POSITIVE_TEMPLATES = [
    "内容丰富，种草体验很好",
    "搜索准确，找东西方便多了",
    "界面简洁，用起来很顺手",
    "推荐算法不错，经常有好物",
    "社区氛围好，互动很积极",
    "视频流畅，加载很快",
    "购物链路顺畅，下单方便",
    "攻略很实用，收藏了很多",
    "直播体验不错，带货实在",
    "笔记质量高，信息量很大",
]

NEUTRAL_TEMPLATES = [
    "功能还行，中规中矩",
    "偶尔用用，没啥特别感觉",
    "界面还可以，就是偶尔卡顿",
    "一般般，没有惊喜",
    "用了一阵子，感觉普通",
]

CATEGORIES = [
    "功能",
    "性能",
    "内容",
    "广告",
    "客服",
    "账号",
    "搜索",
    "社区",
    "电商",
    "其他",
]
RISK_LABELS = ["高风险", "中风险", "低风险"]


def _sentiment_for(rating: int, rng: random.Random) -> int:
    if rating <= 2:
        return rng.randint(0, 25)
    if rating == 3:
        return rng.randint(25, 60)
    return rng.randint(60, 100)


def build_fixture(rows: int, seed: int = 20260806) -> pd.DataFrame:
    rng = random.Random(seed)
    records = []
    for _ in range(rows):
        rating = rng.choices([1, 2, 3, 4, 5], weights=[8, 12, 20, 30, 30], k=1)[0]
        if rating <= 2:
            template = rng.choice(NEGATIVE_TEMPLATES)
            category = rng.choice(["账号", "客服", "广告", "功能", "内容"])
        elif rating >= 4:
            template = rng.choice(POSITIVE_TEMPLATES)
            category = rng.choice(["内容", "搜索", "社区", "电商", "功能"])
        else:
            template = rng.choice(NEUTRAL_TEMPLATES)
            category = rng.choice(["功能", "内容", "其他"])
        version = rng.choice(["1.8.0", "1.9.0", "2.0.0", "2.1.0"])
        date = (
            pd.Timestamp("2026-06-01") + pd.to_timedelta(rng.randint(0, 59), unit="D")
        ).strftime("%Y-%m-%d")
        sentiment = _sentiment_for(rating, rng)
        risk_label = (
            "高风险"
            if rating <= 2 and sentiment < 20
            else rng.choice(["低风险", "低风险", "低风险", "中风险"])
        )
        records.append(
            {
                "评分": rating,
                "内容": template,
                "版本": version,
                "时间": date,
                "情绪指数": sentiment,
                "问题类别": category,
                "风险标签": risk_label,
            }
        )
    return pd.DataFrame(records)


def main() -> int:
    parser = argparse.ArgumentParser(description="生成固定种子的中文合成评论夹具")
    parser.add_argument("--rows", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=20260806)
    parser.add_argument(
        "--output",
        default=str(PACKAGE_DIR / "fixtures" / "synthetic_10000.csv"),
    )
    args = parser.parse_args()

    dataframe = build_fixture(args.rows, seed=args.seed)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    dataframe.to_csv(output, index=False, encoding="utf-8-sig")
    print(f"生成 {len(dataframe)} 行 → {output}")
    print(f"评分分布:\n{dataframe['评分'].value_counts().sort_index().to_string()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
