"""Reusable Agent evaluation runner (Mock and Live modes).

Usage:

    python -m evaluation.evaluate_agent
    python -m evaluation.evaluate_agent --mode mock --fail-under
    python -m evaluation.evaluate_agent --mode live --output-dir evaluation/reports/live

Mock mode is the default: it never reads ``DEEPSEEK_API_KEY`` and never sends
network requests. Live mode only runs when explicitly requested with
``--mode live`` and requires a configured API key.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from backend.agent.deepseek_client import DeepSeekToolClient
from backend.agent.tool_calling import ControlledToolCallingAgent
from backend.agent.tool_definitions import ALLOWED_TOOL_NAMES
from evaluation.metrics import common_failure_reasons, compute_metrics, evaluate_case
from evaluation.mock_tool_client import MockToolClient
from review_preprocessing import preprocess_reviews
from visual_analysis import prepare_dashboard_data

PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_QUESTIONS_PATH = PACKAGE_DIR / "agent_questions.json"
DEFAULT_DATASET_PATH = PACKAGE_DIR / "fixtures" / "evaluation_reviews.csv"
DEFAULT_REPORTS_DIR = PACKAGE_DIR / "reports"

VALID_ROUTINGS = {"rule", "tool_calling", "rule_fallback"}

FAIL_UNDER_THRESHOLDS = {
    "routing_accuracy": 0.90,
    "required_tool_success_rate": 0.90,
    "argument_accuracy": 0.85,
    "illegal_tool_block_rate": 1.00,
    "fallback_success_rate": 1.00,
    "grounded_number_check_rate": 1.00,
}


def load_questions(path: str | Path) -> list[dict[str, Any]]:
    """Load and normalize the standard question set, validating its structure."""
    raw_data = json.loads(Path(path).read_text(encoding="utf-8"))
    cases = raw_data if isinstance(raw_data, list) else raw_data.get("cases", [])
    if not isinstance(cases, list) or not cases:
        raise ValueError("问题集为空或格式不正确。")

    normalized: list[dict[str, Any]] = []
    for case in cases:
        expected_tools = list(case.get("expected_tools") or [])
        expected_all = list(case.get("expected_tools_all") or [])
        if expected_tools and not expected_all:
            expected_all = expected_tools
        routing = str(case.get("expected_routing") or "rule")
        if routing not in VALID_ROUTINGS:
            raise ValueError(
                f"案例 {case.get('id')} 的 expected_routing 无效：{routing}"
            )
        normalized.append(
            {
                "id": str(case["id"]),
                "category": str(case.get("category") or "other"),
                "question": str(case["question"]),
                "expected_routing": routing,
                "expected_tools_all": expected_all,
                "expected_tools_any": list(case.get("expected_tools_any") or []),
                "forbidden_tools": list(case.get("forbidden_tools") or []),
                "expected_arguments": dict(case.get("expected_arguments") or {}),
                "allow_rule_fallback": bool(case.get("allow_rule_fallback", False)),
                "expects_illegal_tool": bool(case.get("expects_illegal_tool", False)),
                "grounded_number_check": case.get("grounded_number_check"),
                "answer_expectations": dict(case.get("answer_expectations") or {}),
                "mock_plan": dict(case.get("mock_plan") or {}),
                "mock_answer": str(case.get("mock_answer") or ""),
            }
        )

    validate_questions(normalized)
    return normalized


def validate_questions(cases: list[dict[str, Any]]) -> None:
    """Structural validation for the question set."""
    ids = [case["id"] for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("问题集存在重复的案例 ID。")

    for case in cases:
        expected_names = list(case["expected_tools_all"]) + list(
            case["expected_tools_any"]
        )
        for name in expected_names:
            if name not in ALLOWED_TOOL_NAMES:
                raise ValueError(f"案例 {case['id']} 的预期工具不在白名单中：{name}")
        mock_names = [
            str(item.get("name") or "")
            for item in (case["mock_plan"].get("tool_calls") or [])
        ]
        simulates_illegal_tool = case["mock_plan"].get(
            "behavior"
        ) == "illegal_tool" or any(
            name not in ALLOWED_TOOL_NAMES for name in mock_names
        )
        if simulates_illegal_tool and not case["expects_illegal_tool"]:
            raise ValueError(
                f"案例 {case['id']} 模拟了非法工具调用，但未标记 expects_illegal_tool。"
            )
        if case["expects_illegal_tool"] and not simulates_illegal_tool:
            raise ValueError(
                f"案例 {case['id']} 标记了 expects_illegal_tool，"
                "但 mock_plan 未模拟非法工具调用。"
            )
        for name in mock_names:
            if name not in ALLOWED_TOOL_NAMES and case["category"] != "adversarial":
                raise ValueError(
                    f"案例 {case['id']} 在 mock_plan 中使用非法工具 {name}，"
                    "但未标记为 adversarial 对抗案例。"
                )


def load_dataset(path: str | Path) -> pd.DataFrame:
    """Load the evaluation fixture and prepare it exactly like the API does."""
    raw_dataframe = pd.read_csv(Path(path))
    return prepare_dashboard_data(preprocess_reviews(raw_dataframe))


def build_tool_client(mode: str, case: dict[str, Any] | None = None) -> Any:
    """Build the tool client for the requested mode.

    Mock mode never reads the API key and never touches the network.
    Live mode validates the DeepSeek configuration before running.
    """
    if mode == "mock":
        return MockToolClient(
            mock_plan=(case or {}).get("mock_plan") or {},
            mock_answer=(case or {}).get("mock_answer") or "",
        )
    if mode == "live":
        from ai_analysis import load_ai_config

        config = load_ai_config()
        if config.get("provider") != "deepseek":
            raise RuntimeError("Live 模式要求 AI_PROVIDER=deepseek，当前配置不满足。")
        if not str(config.get("api_key") or "").strip():
            raise RuntimeError(
                "Live 模式缺少 DEEPSEEK_API_KEY，无法调用真实模型；"
                "请配置 API Key 后重试，或使用默认的 Mock 模式。"
            )
        return DeepSeekToolClient()
    raise ValueError(f"未知评估模式：{mode}")


def run_single_case(
    case: dict[str, Any],
    dataframe: pd.DataFrame,
    mode: str,
) -> dict[str, Any]:
    """Run one question through the real controlled Agent with an injected client."""
    client = build_tool_client(mode, case)
    agent = ControlledToolCallingAgent(tool_client=client)
    result = agent.run(
        question=case["question"],
        dataframe=dataframe,
        scope_label="完整上传数据",
    )
    return {
        "routing": result.routing,
        "tool_calls": [trace.model_dump() for trace in result.tool_calls],
        "answer": result.answer,
        "warnings": result.warnings,
        "evidence": result.evidence,
    }


def evaluate(
    questions: list[dict[str, Any]],
    dataframe: pd.DataFrame,
    *,
    mode: str = "mock",
    case_id: str | None = None,
    category: str | None = None,
    question_path: str | Path | None = None,
    dataset_path: str | Path | None = None,
    model_name: str | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Run every (filtered) question and produce summary + per-case outcomes."""
    selected = questions
    if case_id:
        selected = [case for case in selected if case["id"] == case_id]
    if category:
        selected = [case for case in selected if case["category"] == category]
    if not selected:
        raise ValueError("没有匹配指定筛选条件的案例。")

    outcomes: list[dict[str, Any]] = []
    for case in selected:
        try:
            raw = run_single_case(case, dataframe, mode)
        except Exception as exc:  # a case must never abort the whole evaluation
            raw = {
                "routing": "error",
                "tool_calls": [],
                "answer": "",
                "warnings": [f"评估执行异常：{type(exc).__name__}: {exc}"],
                "evidence": {},
            }
        outcomes.append(evaluate_case(case, raw))

    summary = {
        "mode": mode,
        "model": model_name or ("mock" if mode == "mock" else "unknown"),
        "question_set": str(question_path or ""),
        "dataset": str(dataset_path or ""),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "total_cases": len(outcomes),
        "passed_cases": sum(1 for item in outcomes if item["passed"]),
        "failed_cases": sum(1 for item in outcomes if not item["passed"]),
        "metrics": compute_metrics(outcomes),
        "per_category": _per_category(outcomes),
        "common_failure_reasons": common_failure_reasons(outcomes),
    }
    return summary, outcomes


def _per_category(outcomes: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for item in outcomes:
        entry = grouped.setdefault(
            item["category"],
            {"total": 0, "passed": 0, "failed_ids": []},
        )
        entry["total"] += 1
        if item["passed"]:
            entry["passed"] += 1
        else:
            entry["failed_ids"].append(item["id"])
    return grouped


def fail_under_violations(summary: dict[str, Any]) -> list[str]:
    """Return the list of fail-under threshold violations (empty means pass)."""
    metrics = summary.get("metrics") or {}
    violations: list[str] = []
    for name, threshold in FAIL_UNDER_THRESHOLDS.items():
        value = metrics.get(name)
        if value is None:
            violations.append(f"{name}: 无适用案例")
        elif float(value) < threshold:
            violations.append(f"{name}: {value} < {threshold}")
    return violations


def _case_record(outcome: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": outcome["id"],
        "category": outcome["category"],
        "question": outcome["question"],
        "passed": outcome["passed"],
        "expected_routing": outcome["expected_routing"],
        "actual_routing": outcome["actual_routing"],
        "expected_tools": outcome["expected_tools"],
        "actual_tools": outcome["actual_tools"],
        "actual_statuses": outcome["actual_statuses"],
        "argument_checks": outcome["argument_checks"],
        "grounded_number_check": outcome["grounded_number_check"],
        "warnings": outcome["warnings"],
        "failure_reasons": outcome["failure_reasons"],
    }


def write_reports(
    output_dir: str | Path,
    summary: dict[str, Any],
    outcomes: list[dict[str, Any]],
) -> Path:
    """Write summary.json, cases.jsonl and report.md; returns the report dir."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    (output_path / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )

    with (output_path / "cases.jsonl").open("w", encoding="utf-8") as stream:
        for outcome in outcomes:
            stream.write(
                json.dumps(_case_record(outcome), ensure_ascii=False, allow_nan=False)
                + "\n"
            )

    (output_path / "report.md").write_text(
        build_report_md(summary, outcomes), encoding="utf-8"
    )
    return output_path


def build_report_md(
    summary: dict[str, Any],
    outcomes: list[dict[str, Any]],
) -> str:
    """Human-readable markdown report."""
    metrics = summary["metrics"]
    lines: list[str] = [
        "# Agent 评估报告",
        "",
        f"- 执行模式：{summary['mode']}",
        f"- 数据集：{summary['dataset'] or '（未记录）'}",
        f"- 模型：{summary['model']}",
        f"- 生成时间：{summary['generated_at']}",
        f"- 总案例数：{summary['total_cases']}",
        f"- 通过：{summary['passed_cases']}（{_percent(summary['passed_cases'], summary['total_cases'])}）",
        f"- 失败：{summary['failed_cases']}",
        "",
        "## 评估指标",
        "",
        "| 指标 | 数值 |",
        "| --- | --- |",
    ]
    metric_labels = {
        "routing_accuracy": "路由准确率",
        "tool_exact_match_rate": "工具完全匹配率（参考）",
        "tool_precision": "工具精确率",
        "tool_recall": "工具召回率",
        "tool_f1": "工具 F1",
        "required_tool_success_rate": "必需工具成功率",
        "any_tool_success_rate": "任选工具成功率",
        "argument_accuracy": "参数提取准确率",
        "illegal_tool_block_rate": "非法工具拦截率",
        "fallback_success_rate": "降级成功率",
        "grounded_number_check_rate": "数字可信度校验率",
        "answer_constraint_pass_rate": "回答约束通过率",
    }
    for name, label in metric_labels.items():
        value = metrics.get(name)
        lines.append(f"| {label} | {value if value is not None else 'N/A'} |")

    lines.extend(
        [
            "",
            "## 按问题类别表现",
            "",
            "| 类别 | 通过 | 总案例 | 通过率 | 失败案例 |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for category, entry in sorted(summary["per_category"].items()):
        total = entry["total"]
        passed = entry["passed"]
        failed = "、".join(entry["failed_ids"]) or "-"
        lines.append(
            f"| {category} | {passed} | {total} | {_percent(passed, total)} | {failed} |"
        )

    failed_outcomes = [item for item in outcomes if not item["passed"]]
    lines.extend(["", "## 失败案例", ""])
    if failed_outcomes:
        for item in failed_outcomes:
            reasons = "；".join(item["failure_reasons"]) or "未知原因"
            lines.append(f"- `{item['id']}` {item['question']} → {reasons}")
    else:
        lines.append("- 无失败案例。")

    reasons = summary.get("common_failure_reasons") or {}
    lines.extend(["", "## 常见失败原因", ""])
    if reasons:
        for reason, count in reasons.items():
            lines.append(f"- {reason}（{count} 次）")
    else:
        lines.append("- 无。")

    lines.extend(
        [
            "",
            "## 当前限制",
            "",
            "- 评估基于固定问题集与固定数据集，不随线上数据变化。",
            "- Mock 模式只验证系统机制（路由、白名单、参数、降级、数字校验），不评估模型文本质量。",
            "- Live 模式结果依赖模型表现，可能随模型版本波动，未启用 fail-under。",
            "- 回答约束检查为关键词规则，不使用 LLM Judge。",
            "- 无法判断类问题要求回答明确表达数据不足，当前基线可能因此失败，属于测量结果而非缺陷。",
        ]
    )
    return "\n".join(lines) + "\n"


def _percent(passed: int, total: int) -> str:
    if total == 0:
        return "N/A"
    return f"{passed / total * 100:.1f}%"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Agent 自动化评估（Mock / Live 模式）",
    )
    parser.add_argument(
        "--mode",
        choices=("mock", "live"),
        default="mock",
        help="评估模式，默认 mock（不调用真实 DeepSeek）",
    )
    parser.add_argument("--questions", default=str(DEFAULT_QUESTIONS_PATH))
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET_PATH))
    parser.add_argument(
        "--output-dir",
        default=None,
        help="报告输出目录，默认 evaluation/reports/<时间戳>",
    )
    parser.add_argument("--case-id", default=None, help="只执行指定案例 ID")
    parser.add_argument("--category", default=None, help="只执行指定问题类别")
    parser.add_argument(
        "--fail-under",
        action="store_true",
        help="Mock 模式下低于最低阈值时返回非 0 状态码",
    )
    return parser.parse_args(argv)


def run_main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    try:
        questions = load_questions(args.questions)
        dataframe = load_dataset(args.dataset)
    except (OSError, ValueError) as exc:
        print(f"评估准备失败：{exc}", file=sys.stderr)
        return 2

    model_name = "mock"
    if args.mode == "live":
        try:
            client = build_tool_client("live")
            del client  # per-case clients are built inside run_single_case
            from ai_analysis import load_ai_config

            model_name = str(load_ai_config().get("model") or "unknown")
        except RuntimeError as exc:
            print(f"Live 模式准备失败：{exc}", file=sys.stderr)
            print(
                "请配置 DEEPSEEK_API_KEY 后重试，或使用 --mode mock。", file=sys.stderr
            )
            return 2

    try:
        summary, outcomes = evaluate(
            questions,
            dataframe,
            mode=args.mode,
            case_id=args.case_id,
            category=args.category,
            question_path=args.questions,
            dataset_path=args.dataset,
            model_name=model_name,
        )
    except ValueError as exc:
        print(f"评估执行失败：{exc}", file=sys.stderr)
        return 2

    exit_code = 0
    if args.mode == "mock" and args.fail_under:
        violations = fail_under_violations(summary)
        summary["fail_under"] = {
            "applied": True,
            "passed": not violations,
            "violations": violations,
        }
        if violations:
            print("fail-under 阈值未达标：", file=sys.stderr)
            for violation in violations:
                print(f"  - {violation}", file=sys.stderr)
            exit_code = 1
    elif args.fail_under:
        print("Live 模式默认不启用 fail-under，本次跳过阈值检查。")

    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        output_dir = DEFAULT_REPORTS_DIR / stamp
    report_dir = write_reports(output_dir, summary, outcomes)

    print(f"评估完成：mode={summary['mode']} model={summary['model']}")
    print(
        f"案例：{summary['passed_cases']}/{summary['total_cases']} 通过，"
        f"{summary['failed_cases']} 失败"
    )
    for name, value in summary["metrics"].items():
        print(f"  {name}: {value if value is not None else 'N/A'}")
    print(f"报告目录：{report_dir}")
    return exit_code


if __name__ == "__main__":
    sys.exit(run_main())
