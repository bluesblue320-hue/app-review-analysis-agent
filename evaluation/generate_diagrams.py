"""Generate architecture and failure-degradation diagrams as SVG.

Usage:
    python -m evaluation.generate_diagrams
Outputs:
    docs/architecture.svg
    docs/degradation.svg
"""

from __future__ import annotations

from pathlib import Path

DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"


def _svg_doc(width: int, height: int, body: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
        f'height="{height}" viewBox="0 0 {width} {height}" '
        f'font-family="Segoe UI, Microsoft YaHei, sans-serif">\n{body}\n</svg>\n'
    )


def _box(
    x: int, y: int, w: int, h: int, label: str, fill: str = "#f1f5f9", sub: str = ""
) -> str:
    lines = f'<text x="{x + w / 2}" y="{y + h / 2 - (8 if sub else 0)}" '
    lines += f'text-anchor="middle" font-size="14" fill="#0f172a">{label}</text>'
    if sub:
        lines += f'\n<text x="{x + w / 2}" y="{y + h / 2 + 16}" text-anchor="middle" '
        lines += f'font-size="11" fill="#64748b">{sub}</text>'
    return (
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="{fill}" '
        f'stroke="#cbd5e1" stroke-width="1.5"/>{lines}'
    )


def _arrow(x1: int, y1: int, x2: int, y2: int, label: str = "") -> str:
    marker = (
        '<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" '
        'orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="#94a3b8"/></marker></defs>'
    )
    lines = f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#94a3b8" '
    lines += 'stroke-width="1.5" marker-end="url(#arrow)"/>'
    if label:
        mx, my = (x1 + x2) // 2, (y1 + y2) // 2
        lines += f'\n<text x="{mx}" y="{my - 6}" text-anchor="middle" font-size="10" '
        lines += f'fill="#475569">{label}</text>'
    return marker + lines


def architecture() -> str:
    body = _box(
        40,
        30,
        220,
        60,
        "浏览器 / Streamlit",
        "#e0f2fe",
        "app.py → frontend/components.py",
    )
    body += _box(40, 130, 220, 60, "API Client", "#e0f2fe", "令牌仅存 Session")
    body += _arrow(150, 90, 150, 130)

    body += _box(360, 30, 260, 60, "FastAPI", "#fef3c7", "/api/v1/*")
    body += _arrow(260, 60, 360, 60, "HTTP / Bearer")

    body += _box(
        360,
        130,
        260,
        50,
        "Dataset / Insight Repository",
        "#fef3c7",
        "内存 | SQLAlchemy",
    )
    body += _box(
        360, 210, 260, 50, "确定性分析", "#fef3c7", "评分过滤/情绪/关键词/趋势"
    )
    body += _box(
        360, 290, 260, 50, "AI 洞察 + Redis 缓存/短锁", "#fef3c7", "fingerprint 去重"
    )
    body += _box(
        360, 370, 260, 60, "受控 Agent", "#fef3c7", "Direct | LangChain 双 Adapter"
    )
    body += _arrow(490, 90, 490, 130)
    body += _arrow(490, 180, 490, 210)
    body += _arrow(490, 260, 490, 290)
    body += _arrow(490, 340, 490, 370)

    body += _box(700, 130, 160, 50, "PostgreSQL 16", "#dcfce7", "Alembic 迁移")
    body += _arrow(620, 155, 700, 155)
    body += _box(700, 290, 160, 50, "Redis 7", "#dcfce7", "缓存 + 短锁")
    body += _arrow(620, 315, 700, 315)

    body += _box(700, 370, 160, 60, "DeepSeek API", "#fce7f3", "Direct | ChatDeepSeek")
    body += _arrow(620, 400, 700, 400)

    return _svg_doc(900, 470, body)


def degradation() -> str:
    body = _box(40, 30, 240, 50, "Agent 请求", "#e0f2fe")
    body += _box(40, 120, 240, 50, "规则快速路由", "#dcfce7", "简单问题，不调模型")
    body += _box(
        40, 210, 240, 50, "受控 Tool Calling", "#fef3c7", "双 Adapter，最多 3 次"
    )
    body += _arrow(160, 80, 160, 120)
    body += _arrow(160, 170, 160, 210)

    body += _box(
        380,
        210,
        240,
        130,
        "规则降级（fallback）",
        "#fee2e2",
        "模型未配置/超时/非法工具/校验失败",
    )
    body += _arrow(280, 235, 380, 235, "失败")

    body += _box(380, 60, 240, 50, "工具执行", "#e0f2fe", "白名单 + Pydantic")
    body += _arrow(280, 235, 380, 85, "成功")

    body += _box(380, 390, 240, 50, "Redis 故障", "#fee2e2", "缓存 miss / 锁放行")
    body += _box(700, 390, 180, 50, "PostgreSQL 兜底", "#dcfce7", "唯一约束保单行")
    body += _arrow(620, 415, 700, 415)

    body += _box(700, 60, 180, 50, "PG 不可用", "#fee2e2", "/ready → 503")
    body += _arrow(620, 85, 700, 85)

    return _svg_doc(920, 480, body)


def main() -> int:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    (DOCS_DIR / "architecture.svg").write_text(architecture(), encoding="utf-8")
    (DOCS_DIR / "degradation.svg").write_text(degradation(), encoding="utf-8")
    print("已生成 docs/architecture.svg 与 docs/degradation.svg")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
