"""Metrics for the Agent evaluation framework.

Every metric is defined over per-case check results produced by
``evaluate_case``. Aggregate metrics are plain rates (mean over the relevant
cases); a metric is ``None`` when no case contributes to its denominator.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from backend.agent.tool_definitions import ALLOWED_TOOL_NAMES

UNCERTAINTY_PHRASES = (
    "无法判断",
    "不足以判断",
    "无法回答",
    "数据不足",
    "信息不足",
    "暂时无法",
    "无法确定",
    "无法预估",
    "不确定",
    "不能判断",
    "难以判断",
)

GROUNDED_FALLBACK_WARNING = "回答校验失败"


def _normalize_list(items: list[Any]) -> list[str]:
    return sorted({str(item).strip() for item in items})


def _values_match(expected: Any, actual: Any) -> bool:
    """Compare a single expected argument against the actual validated value.

    List order is ignored; strings are stripped before comparison.
    """
    if isinstance(expected, list):
        if not isinstance(actual, list):
            return False
        return _normalize_list(expected) == _normalize_list(actual)
    if isinstance(expected, str):
        return str(actual).strip() == expected.strip()
    return actual == expected


def compare_arguments(
    expected_arguments: dict[str, Any],
    actual_arguments: dict[str, Any],
) -> tuple[bool, dict[str, bool]]:
    """Compare the key arguments actually used by a tool with the expected ones."""
    checks: dict[str, bool] = {}
    overall = True
    for key, expected_value in expected_arguments.items():
        match = _values_match(expected_value, actual_arguments.get(key))
        checks[str(key)] = bool(match)
        overall = overall and bool(match)
    return overall, checks


def _answer_constraint_checks(
    answer: str,
    answer_expectations: dict[str, Any],
) -> dict[str, bool]:
    must_contain_any = list(answer_expectations.get("must_contain_any") or [])
    must_not_contain = list(answer_expectations.get("must_not_contain") or [])
    requires_uncertainty = bool(
        answer_expectations.get("requires_uncertainty", False)
    )
    return {
        "must_contain_ok": not must_contain_any
        or any(item in answer for item in must_contain_any),
        "must_not_contain_ok": not any(item in answer for item in must_not_contain),
        "uncertainty_ok": not requires_uncertainty
        or any(phrase in answer for phrase in UNCERTAINTY_PHRASES),
    }


def evaluate_case(case: dict[str, Any], raw: dict[str, Any]) -> dict[str, Any]:
    """Evaluate one question run against its expected behaviour."""
    answer = str(raw.get("answer") or "")
    warnings = list(raw.get("warnings") or [])
    actual_routing = str(raw.get("routing") or "error")
    tool_calls = list(raw.get("tool_calls") or [])

    success_tools = [
        str(item["name"])
        for item in tool_calls
        if item.get("status") == "success"
    ]
    expected_all = list(case.get("expected_tools_all") or [])
    expected_any = list(case.get("expected_tools_any") or [])
    expected_set = set(expected_all) | set(expected_any)
    actual_set = set(success_tools)
    forbidden_tools = list(case.get("forbidden_tools") or [])
    expected_arguments = case.get("expected_arguments") or {}
    category = str(case.get("category") or "other")
    grounded_check = case.get("grounded_number_check")

    checks: dict[str, bool] = {}
    failure_reasons: list[str] = []

    checks["routing_ok"] = (
        actual_routing == case.get("expected_routing")
        or (
            actual_routing == "rule_fallback"
            and bool(case.get("allow_rule_fallback", False))
        )
    )
    if not checks["routing_ok"]:
        failure_reasons.append(
            f"路由不正确：期望 {case.get('expected_routing')}，实际 {actual_routing}"
        )

    checks["required_tools_ok"] = not expected_all or set(expected_all) <= actual_set
    if not checks["required_tools_ok"]:
        missing = sorted(set(expected_all) - actual_set)
        failure_reasons.append(f"缺少必需工具调用：{missing}")

    checks["any_tools_ok"] = not expected_any or bool(actual_set & set(expected_any))
    if not checks["any_tools_ok"]:
        failure_reasons.append("期望的任一工具均未被调用")

    # Exact match: all required tools present, the any-group satisfied by at
    # least one candidate, and no extra unreasonable tool was called.
    exact_match = (
        set(expected_all) <= actual_set
        and (not expected_any or bool(actual_set & set(expected_any)))
        and actual_set <= (set(expected_all) | set(expected_any))
    )

    forbidden_hits = sorted(actual_set & set(forbidden_tools))
    checks["forbidden_ok"] = not forbidden_hits
    if forbidden_hits:
        failure_reasons.append(f"调用了禁止工具：{forbidden_hits}")

    argument_checks: dict[str, dict[str, bool]] = {}
    checks["arguments_ok"] = True
    if expected_arguments:
        for tool_name, tool_args in expected_arguments.items():
            actual_tool_args: dict[str, Any] = {}
            for item in tool_calls:
                if item.get("name") == tool_name and item.get("status") == "success":
                    actual_tool_args = dict(item.get("arguments") or {})
                    break
            tool_ok, tool_checks = compare_arguments(dict(tool_args), actual_tool_args)
            argument_checks[str(tool_name)] = tool_checks
            if not tool_ok:
                checks["arguments_ok"] = False
                failure_reasons.append(f"参数提取不正确：{tool_name}={tool_args}")

    if case.get("expects_illegal_tool"):
        illegal_calls = [
            item for item in tool_calls if str(item["name"]) not in ALLOWED_TOOL_NAMES
        ]
        checks["illegal_block_ok"] = bool(illegal_calls) and all(
            item.get("status") == "rejected" for item in illegal_calls
        )
        if not checks["illegal_block_ok"]:
            failure_reasons.append("非法工具调用未出现或未被拒绝")
    else:
        checks["illegal_block_ok"] = None

    if category == "degradation":
        checks["fallback_ok"] = (
            actual_routing == "rule_fallback"
            and bool(answer)
            and any("降级" in warning for warning in warnings)
        )
        if not checks["fallback_ok"]:
            failure_reasons.append("模型故障后未能安全降级到规则流程")
    else:
        checks["fallback_ok"] = None

    if grounded_check == "must_fail":
        checks["grounded_ok"] = actual_routing == "rule_fallback" and any(
            GROUNDED_FALLBACK_WARNING in warning for warning in warnings
        )
        if not checks["grounded_ok"]:
            failure_reasons.append("包含虚假数字的回答未被拦截")
    elif grounded_check == "pass":
        checks["grounded_ok"] = (
            (
                actual_routing == "tool_calling"
                or (
                    actual_routing == "rule_fallback"
                    and bool(case.get("allow_rule_fallback", False))
                )
            )
            and not any(GROUNDED_FALLBACK_WARNING in w for w in warnings)
        )
        if not checks["grounded_ok"]:
            failure_reasons.append("数字可信度校验未通过")
    else:
        checks["grounded_ok"] = None

    if not case.get("allow_rule_fallback", False) and actual_routing == "rule_fallback":
        checks["fallback_forbidden_ok"] = False
        failure_reasons.append("该案例不允许降级，但实际发生了规则降级")
    else:
        checks["fallback_forbidden_ok"] = True

    answer_expectations = case.get("answer_expectations") or {}
    answer_checks = _answer_constraint_checks(answer, answer_expectations)
    if answer_expectations:
        checks["answer_ok"] = all(answer_checks.values())
        if answer_checks.get("must_contain_ok") is False:
            failure_reasons.append("回答缺少要求包含的内容")
        if answer_checks.get("must_not_contain_ok") is False:
            failure_reasons.append("回答包含禁止出现的内容")
        if answer_checks.get("uncertainty_ok") is False:
            failure_reasons.append("当前数据无法判断的问题未明确说明")
    else:
        checks["answer_ok"] = True

    passed = all(value for value in checks.values() if value is not None)
    return {
        "id": str(case["id"]),
        "category": category,
        "question": str(case["question"]),
        "passed": bool(passed),
        "failure_reasons": failure_reasons,
        "expected_routing": str(case.get("expected_routing") or "rule"),
        "actual_routing": actual_routing,
        "expected_tools": sorted(expected_set),
        "expected_tools_all": expected_all,
        "expected_tools_any": expected_any,
        "actual_tools": sorted(actual_set),
        "exact_match": bool(exact_match),
        "expects_illegal_tool": bool(case.get("expects_illegal_tool")),
        "actual_statuses": {
            str(item["name"]): item.get("status") for item in tool_calls
        },
        "argument_checks": argument_checks,
        "grounded_number_check": grounded_check,
        "checks": checks,
        "warnings": warnings,
        "answer": answer,
    }


def _rate(passed: float, total: int) -> float | None:
    if total == 0:
        return None
    return round(passed / total, 4)


def compute_metrics(outcomes: list[dict[str, Any]]) -> dict[str, float | None]:
    """Compute the aggregate evaluation metrics over all case outcomes."""
    total = len(outcomes)
    routing_ok = sum(1 for item in outcomes if item["checks"]["routing_ok"])

    tool_cases = [item for item in outcomes if item["expected_tools"]]
    required_cases = [item for item in outcomes if item["expected_tools_all"]]
    any_cases = [item for item in outcomes if item["expected_tools_any"]]
    argument_cases = [item for item in outcomes if item["argument_checks"]]
    degradation_cases = [item for item in outcomes if item["category"] == "degradation"]
    grounded_cases = [item for item in outcomes if item["grounded_number_check"]]

    precision_sum = recall_sum = f1_sum = exact_sum = 0.0
    for item in tool_cases:
        actual = set(item["actual_tools"])
        required = set(item["expected_tools_all"])
        any_candidates = set(item["expected_tools_any"])
        allowed = required | any_candidates

        # Precision: calls belonging to the required or any candidates are
        # considered reasonable tools.
        correct = len(actual & allowed)
        precision_i = correct / len(actual) if actual else 0.0

        # Recall: required tools are counted individually; the any-group is
        # satisfied as a whole once at least one candidate was called.
        required_hits = len(required & actual)
        any_hit = 1.0 if (any_candidates and (actual & any_candidates)) else 0.0
        recall_denominator = len(required) + (1 if any_candidates else 0)
        recall_i = (
            (required_hits + any_hit) / recall_denominator
            if recall_denominator
            else 0.0
        )
        f1_i = (
            (2 * precision_i * recall_i / (precision_i + recall_i))
            if (precision_i + recall_i) > 0
            else 0.0
        )
        precision_sum += precision_i
        recall_sum += recall_i
        f1_sum += f1_i
        exact_sum += 1 if item["exact_match"] else 0

    required_ok = sum(
        1 for item in required_cases if item["checks"]["required_tools_ok"]
    )
    any_ok = sum(1 for item in any_cases if item["checks"]["any_tools_ok"])
    argument_ok = sum(
        1 for item in argument_cases if item["checks"]["arguments_ok"]
    )
    illegal_cases = [item for item in outcomes if item["expects_illegal_tool"]]
    illegal_ok = sum(
        1 for item in illegal_cases if item["checks"]["illegal_block_ok"]
    )
    fallback_ok = sum(
        1 for item in degradation_cases if item["checks"]["fallback_ok"]
    )
    grounded_ok = sum(
        1 for item in grounded_cases if item["checks"]["grounded_ok"]
    )
    answer_ok = sum(1 for item in outcomes if item["checks"]["answer_ok"])

    return {
        "routing_accuracy": _rate(routing_ok, total),
        "tool_exact_match_rate": _rate(exact_sum, len(tool_cases)),
        "tool_precision": _rate(precision_sum, len(tool_cases)),
        "tool_recall": _rate(recall_sum, len(tool_cases)),
        "tool_f1": _rate(f1_sum, len(tool_cases)),
        "required_tool_success_rate": _rate(required_ok, len(required_cases)),
        "any_tool_success_rate": _rate(any_ok, len(any_cases)),
        "argument_accuracy": _rate(argument_ok, len(argument_cases)),
        "illegal_tool_block_rate": _rate(illegal_ok, len(illegal_cases)),
        "fallback_success_rate": _rate(fallback_ok, len(degradation_cases)),
        "grounded_number_check_rate": _rate(grounded_ok, len(grounded_cases)),
        "answer_constraint_pass_rate": _rate(answer_ok, total),
    }


def common_failure_reasons(outcomes: list[dict[str, Any]]) -> dict[str, int]:
    reasons: Counter[str] = Counter()
    for item in outcomes:
        for reason in item["failure_reasons"]:
            reasons[reason] += 1
    return dict(reasons.most_common())
