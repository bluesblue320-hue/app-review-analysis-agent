import type { EChartsOption } from "echarts";

import type { IssuePriority as IssuePriorityType } from "../../types/api";
import { EmptyState, Panel } from "../common/Panel";
import { EChart } from "./EChart";

export function IssuePriority({ items }: { items: IssuePriorityType[] }) {
  if (!items.length) return <Panel title="问题优先级" eyebrow="Action queue"><EmptyState title="暂无优先级数据" detail="请调整筛选范围后重试。" /></Panel>;
  const option: EChartsOption = {
    backgroundColor: "transparent",
    tooltip: { trigger: "axis" },
    grid: { left: 90, right: 20, top: 10, bottom: 28 },
    xAxis: { type: "value", axisLabel: { color: "#94a3b8" }, splitLine: { lineStyle: { color: "rgba(51,65,85,.45)" } } },
    yAxis: { type: "category", inverse: true, data: items.map((item) => item.category), axisLabel: { color: "#94a3b8" }, axisLine: { lineStyle: { color: "#334155" } } },
    series: [{ type: "bar", data: items.map((item) => item.priority_score), itemStyle: { color: "#f59e0b", borderRadius: [0, 5, 5, 0] } }],
  };
  return (
    <Panel title="问题优先级" eyebrow="Action queue">
      <EChart option={option} label="问题优先级图" height={230} />
      <div className="table-wrap mt-4">
        <table><thead><tr><th>问题类型</th><th>优先级</th><th>严重度</th><th>评论数</th><th>平均星级</th><th>平均情绪</th><th>建议</th></tr></thead>
          <tbody>{items.map((item) => <tr key={item.category}><td className="font-medium text-slate-200">{item.category}</td><td>{item.priority_score.toFixed(2)}</td><td><span className="status-pill">{item.severity}</span></td><td>{item.review_count}</td><td>{item.average_rating.toFixed(2)}</td><td>{item.average_sentiment.toFixed(1)}</td><td className="max-w-72 text-slate-400">{item.ai_recommendation || "—"}</td></tr>)}</tbody>
        </table>
      </div>
    </Panel>
  );
}
