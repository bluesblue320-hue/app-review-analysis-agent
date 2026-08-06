"""Tests for the Agent evaluation framework (Mock mode only; never calls DeepSeek)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import evaluation.evaluate_agent as evaluation_module
import evaluation.metrics as metrics_module
from backend.agent.tool_calling import ControlledToolCallingAgent
from backend.agent.tool_definitions import ALLOWED_TOOL_NAMES
from evaluation.evaluate_agent import (
    build_tool_client,
    evaluate,
    fail_under_violations,
    load_dataset,
    load_questions,
    run_main,
    validate_questions,
    write_reports,
)
from evaluation.mock_tool_client import MockToolClient

QUESTIONS_PATH = (
    Path(__file__).resolve().parents[1] / "evaluation" / "agent_questions.json"
)
DATASET_PATH = (
    Path(__file__).resolve().parents[1]
    / "evaluation"
    / "fixtures"
    / "evaluation_reviews.csv"
)

EXPECTED_BASELINE_FAILURES = {
    "uncertain_001",
    "uncertain_002",
    "uncertain_003",
    "uncertain_004",
    "adversarial_004",
}


@pytest.fixture(scope="module")
def questions():
    return load_questions(QUESTIONS_PATH)


@pytest.fixture(scope="module")
def dataframe():
    return load_dataset(DATASET_PATH)


@pytest.fixture(scope="module")
def evaluation_results(dataframe, questions):
    return evaluate(questions, dataframe, mode="mock")


def test_question_json_loads(questions):
    assert isinstance(questions, list)
    assert len(questions) >= 40


def test_case_ids_unique(questions):
    ids = [case["id"] for case in questions]
    assert len(ids) == len(set(ids))


def test_all_tool_names_from_whitelist(questions):
    for case in questions:
        expected_names = list(case["expected_tools_all"]) + list(
            case["expected_tools_any"]
        )
        for name in expected_names:
            assert name in ALLOWED_TOOL_NAMES, f"{case['id']} 工具不在白名单：{name}"


def test_illegal_tool_cases_marked_as_adversarial(questions):
    validate_questions(questions)
    for case in questions:
        mock_names = [
            str(item.get("name") or "")
            for item in (case["mock_plan"].get("tool_calls") or [])
        ]
        for name in mock_names:
            if name not in ALLOWED_TOOL_NAMES:
                assert case["category"] == "adversarial", (
                    f"案例 {case['id']} 使用非法工具 {name} 但类别不是 adversarial"
                )


def test_mock_mode_never_contacts_network(monkeypatch, dataframe):
    def boom(*args, **kwargs):
        raise AssertionError("Mock 模式不应访问网络或读取 AI 配置")

    monkeypatch.setattr("ai_analysis.load_ai_config", boom)
    monkeypatch.setattr("requests.post", boom)

    case = {
        "question": "请综合诊断当前评论表现。",
        "mock_plan": {"behavior": "timeout"},
        "mock_answer": "",
    }
    client = MockToolClient(case["mock_plan"], case["mock_answer"])
    agent = ControlledToolCallingAgent(tool_client=client)
    result = agent.run(
        question=case["question"],
        dataframe=dataframe,
        scope_label="完整上传数据",
    )
    assert result.routing == "rule_fallback"
    assert client.plan_count == 1


def test_mock_mode_does_not_require_api_key(monkeypatch, dataframe, questions):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    summary, _ = evaluate(questions, dataframe, mode="mock")
    assert summary["mode"] == "mock"


def test_routing_accuracy(evaluation_results):
    summary, _ = evaluation_results
    assert summary["metrics"]["routing_accuracy"] == 1.0


def test_tool_precision_recall_f1(evaluation_results):
    summary, _ = evaluation_results
    metrics = summary["metrics"]
    assert metrics["tool_precision"] == 1.0
    assert metrics["tool_recall"] == 1.0
    assert metrics["tool_f1"] == 1.0
    assert metrics["tool_exact_match_rate"] == 1.0


def test_argument_comparison_logic():
    assert metrics_module.compare_arguments(
        {"versions": ["1.9.0", "2.0.0"]},
        {"versions": ["2.0.0", "1.9.0"]},
    ) == (True, {"versions": True})
    assert metrics_module.compare_arguments({"limit": 5}, {"limit": 5}) == (
        True,
        {"limit": True},
    )
    assert metrics_module.compare_arguments({"limit": 5}, {"limit": 10}) == (
        False,
        {"limit": False},
    )


def test_parameter_extraction_passes(evaluation_results):
    summary, outcomes = evaluation_results
    param_cases = [
        item for item in outcomes if item["category"] == "parameter_extraction"
    ]
    assert len(param_cases) == 5
    assert all(item["passed"] for item in param_cases)
    assert summary["metrics"]["argument_accuracy"] == 1.0


def test_illegal_tool_block_rate(evaluation_results):
    summary, outcomes = evaluation_results
    assert summary["metrics"]["illegal_tool_block_rate"] == 1.0
    flagged = [item for item in outcomes if item["expects_illegal_tool"]]
    assert len(flagged) == 3
    assert {item["id"] for item in flagged} == {
        "adversarial_001",
        "adversarial_003",
        "degradation_004",
    }
    for item in flagged:
        assert item["checks"]["illegal_block_ok"] is True
    for item in outcomes:
        if not item["expects_illegal_tool"]:
            assert item["checks"]["illegal_block_ok"] is None


def test_fallback_success_rate(evaluation_results):
    summary, outcomes = evaluation_results
    assert summary["metrics"]["fallback_success_rate"] == 1.0
    degradation = [item for item in outcomes if item["category"] == "degradation"]
    assert len(degradation) == 6
    for item in degradation:
        assert item["checks"]["fallback_ok"] is True
        assert item["actual_routing"] == "rule_fallback"


def test_grounded_number_check_rate(evaluation_results):
    summary, _ = evaluation_results
    assert summary["metrics"]["grounded_number_check_rate"] == 1.0


def test_illegal_tool_metric_null_without_applicable_cases(dataframe, questions):
    summary, _ = evaluate(questions, dataframe, mode="mock", case_id="routing_001")
    assert summary["metrics"]["illegal_tool_block_rate"] is None


def test_illegal_tool_must_be_rejected():
    case = {
        "id": "crafted_illegal",
        "category": "adversarial",
        "question": "q",
        "expected_routing": "rule_fallback",
        "expected_tools_all": [],
        "expected_tools_any": [],
        "forbidden_tools": ["delete_dataset"],
        "expected_arguments": {},
        "allow_rule_fallback": True,
        "expects_illegal_tool": True,
        "grounded_number_check": None,
        "answer_expectations": {},
    }
    accepted_raw = {
        "routing": "rule_fallback",
        "tool_calls": [
            {"name": "delete_dataset", "arguments": {}, "status": "success"}
        ],
        "answer": "已降级。",
        "warnings": ["已降级到原规则工作流。"],
    }
    outcome = metrics_module.evaluate_case(case, accepted_raw)
    assert outcome["checks"]["illegal_block_ok"] is False
    assert not outcome["passed"]

    no_call_raw = {
        "routing": "rule_fallback",
        "tool_calls": [],
        "answer": "已降级。",
        "warnings": ["已降级到原规则工作流。"],
    }
    outcome = metrics_module.evaluate_case(case, no_call_raw)
    assert outcome["checks"]["illegal_block_ok"] is False


def test_expects_illegal_tool_flag_validation():
    base = {
        "id": "crafted",
        "category": "adversarial",
        "question": "q",
        "expected_routing": "rule_fallback",
        "expected_tools_all": [],
        "expected_tools_any": [],
        "forbidden_tools": [],
        "expected_arguments": {},
        "allow_rule_fallback": True,
        "expects_illegal_tool": False,
        "mock_plan": {},
        "mock_answer": "",
    }
    with pytest.raises(ValueError, match="expects_illegal_tool"):
        validate_questions(
            [
                {
                    **base,
                    "mock_plan": {
                        "tool_calls": [
                            {"id": "c1", "name": "delete_dataset", "arguments": {}}
                        ]
                    },
                }
            ]
        )
    with pytest.raises(ValueError, match="expects_illegal_tool"):
        validate_questions([{**base, "mock_plan": {"behavior": "illegal_tool"}}])
    with pytest.raises(ValueError, match="expects_illegal_tool"):
        validate_questions(
            [
                {
                    **base,
                    "expects_illegal_tool": True,
                    "mock_plan": {"behavior": "timeout"},
                }
            ]
        )


def _fabricated_outcome(
    expected_all: list[str],
    expected_any: list[str],
    actual_tools: list[str],
    exact_match: bool,
) -> dict:
    """Minimal outcome shape used to unit-test aggregate metric math."""
    actual_set = set(actual_tools)
    return {
        "expected_tools": sorted(set(expected_all) | set(expected_any)),
        "expected_tools_all": expected_all,
        "expected_tools_any": expected_any,
        "actual_tools": actual_tools,
        "exact_match": exact_match,
        "expects_illegal_tool": False,
        "grounded_number_check": None,
        "category": "complex_multi_tool",
        "argument_checks": {},
        "checks": {
            "routing_ok": True,
            "required_tools_ok": set(expected_all) <= actual_set,
            "any_tools_ok": not expected_any or bool(set(expected_any) & actual_set),
            "arguments_ok": True,
            "illegal_block_ok": None,
            "fallback_ok": None,
            "grounded_ok": None,
            "answer_ok": True,
        },
    }


def test_any_group_tool_recall_semantics():
    outcomes = [
        _fabricated_outcome(
            expected_all=["a"],
            expected_any=["b", "c"],
            actual_tools=["b"],
            exact_match=False,
        )
    ]
    metrics = metrics_module.compute_metrics(outcomes)
    assert metrics["tool_precision"] == 1.0
    assert metrics["tool_recall"] == 0.5
    assert metrics["tool_exact_match_rate"] == 0.0
    assert metrics["required_tool_success_rate"] == 0.0
    assert metrics["any_tool_success_rate"] == 1.0


def test_exact_match_any_group_semantics():
    outcomes = [
        _fabricated_outcome(
            expected_all=["a"],
            expected_any=["b", "c"],
            actual_tools=["a", "c"],
            exact_match=True,
        )
    ]
    metrics = metrics_module.compute_metrics(outcomes)
    assert metrics["tool_exact_match_rate"] == 1.0
    assert metrics["tool_precision"] == 1.0
    assert metrics["tool_recall"] == 1.0
    assert metrics["required_tool_success_rate"] == 1.0
    assert metrics["any_tool_success_rate"] == 1.0


def test_ungrounded_answer_triggers_fallback(dataframe):
    case = {
        "question": "请综合诊断当前评论表现。",
        "mock_plan": {"behavior": "ungrounded_answer"},
        "mock_answer": "",
    }
    client = MockToolClient(case["mock_plan"], case["mock_answer"])
    agent = ControlledToolCallingAgent(tool_client=client)
    result = agent.run(
        question=case["question"],
        dataframe=dataframe,
        scope_label="完整上传数据",
    )
    assert result.routing == "rule_fallback"
    assert any("回答校验失败" in warning for warning in result.warnings)


def test_baseline_regression(evaluation_results):
    summary, outcomes = evaluation_results
    failed_ids = {item["id"] for item in outcomes if not item["passed"]}
    # 总案例数与通过数下限
    assert summary["total_cases"] == 46
    assert summary["passed_cases"] >= 41
    # 不允许出现已知失败集合之外的新失败；已知失败未来修复后通过也允许
    assert failed_ids <= EXPECTED_BASELINE_FAILURES
    # 核心 fail-under 指标不得低于阈值
    assert fail_under_violations(summary) == []


def test_report_files_generated(tmp_path, evaluation_results):
    summary, outcomes = evaluation_results
    report_dir = write_reports(tmp_path, summary, outcomes)
    assert (report_dir / "summary.json").exists()
    assert (report_dir / "cases.jsonl").exists()
    assert (report_dir / "report.md").exists()


def test_summary_json_parseable(evaluation_results, tmp_path):
    summary, outcomes = evaluation_results
    report_dir = write_reports(tmp_path, summary, outcomes)
    loaded = json.loads((report_dir / "summary.json").read_text(encoding="utf-8"))
    assert loaded["total_cases"] == 46
    assert "metrics" in loaded
    assert "NaN" not in (report_dir / "summary.json").read_text(encoding="utf-8")
    assert "Infinity" not in (report_dir / "summary.json").read_text(encoding="utf-8")


def test_cases_jsonl_lines_are_valid_json(evaluation_results, tmp_path):
    summary, outcomes = evaluation_results
    report_dir = write_reports(tmp_path, summary, outcomes)
    lines = [
        line
        for line in (report_dir / "cases.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    assert len(lines) == 46
    for line in lines:
        record = json.loads(line)
        assert record["id"]
        assert "passed" in record
        assert "expected_routing" in record
        assert "actual_routing" in record


def test_case_id_filter(dataframe, questions):
    summary, outcomes = evaluate(
        questions, dataframe, mode="mock", case_id="routing_001"
    )
    assert summary["total_cases"] == 1
    assert outcomes[0]["id"] == "routing_001"


def test_category_filter(dataframe, questions):
    summary, outcomes = evaluate(
        questions, dataframe, mode="mock", category="complex_multi_tool"
    )
    assert summary["total_cases"] == 6
    assert {item["id"] for item in outcomes} == {
        f"complex_00{index}" for index in range(1, 7)
    }


def test_fail_under_passes_for_mock_baseline(evaluation_results, tmp_path):
    summary, _ = evaluation_results
    assert fail_under_violations(summary) == []
    assert (
        run_main(
            [
                "--mode",
                "mock",
                "--fail-under",
                "--output-dir",
                str(tmp_path),
            ]
        )
        == 0
    )
    written = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert written["fail_under"]["passed"] is True


def test_fail_under_returns_nonzero_below_threshold(monkeypatch, tmp_path):
    def broken_violations(summary):
        return ["routing_accuracy: 0.5 < 0.9"]

    monkeypatch.setattr(evaluation_module, "fail_under_violations", broken_violations)
    assert (
        run_main(
            [
                "--mode",
                "mock",
                "--fail-under",
                "--output-dir",
                str(tmp_path),
            ]
        )
        == 1
    )


def test_default_mode_is_mock(tmp_path):
    assert run_main(["--output-dir", str(tmp_path)]) == 0
    written = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert written["mode"] == "mock"


def test_live_mode_missing_api_key_exits_safely(monkeypatch):
    def empty_config():
        return {
            "provider": "deepseek",
            "model": "deepseek-v4-flash",
            "api_key": "",
            "base_url": "https://api.deepseek.com/chat/completions",
        }

    monkeypatch.setattr("ai_analysis.load_ai_config", empty_config)
    with pytest.raises(RuntimeError, match="DEEPSEEK_API_KEY"):
        build_tool_client("live")
    assert run_main(["--mode", "live"]) == 2


def test_live_mode_requires_explicit_flag_only(evaluation_results):
    summary, _ = evaluation_results
    assert summary["mode"] == "mock"
