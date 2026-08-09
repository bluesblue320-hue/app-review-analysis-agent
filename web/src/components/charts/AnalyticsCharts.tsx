import type { EChartsOption } from "echarts";

import type { AnalyticsSummary } from "../../types/api";
import { EmptyState, Panel } from "../common/Panel";
import { EChart } from "./EChart";

const axis = {
  axisLine: { lineStyle: { color: "#334155" } },
  axisLabel: { color: "#94a3b8" },
  splitLine: { lineStyle: { color: "rgba(51,65,85,.45)" } },
};

function Chart({ option, label }: { option: EChartsOption; label: string }) {
  return <EChart option={option} label={label} />;
}

export function AnalyticsCharts({ summary }: { summary: AnalyticsSummary }) {
  const base: EChartsOption = { backgroundColor: "transparent", textStyle: { color: "#cbd5e1" }, tooltip: { trigger: "axis", backgroundColor: "#0f172a", borderColor: "#334155", textStyle: { color: "#e2e8f0" } }, grid: { left: 40, right: 20, top: 24, bottom: 36 } };
  const rating: EChartsOption = { ...base, xAxis: { ...axis, type: "category", data: summary.rating_distribution.map((item) => `${item.rating} 星`) }, yAxis: { ...axis, type: "value" }, series: [{ type: "bar", data: summary.rating_distribution.map((item) => item.review_count), itemStyle: { color: "#2dd4bf", borderRadius: [5, 5, 0, 0] } }] };
  const sentiment: EChartsOption = { ...base, xAxis: { ...axis, type: "category", data: summary.sentiment_distribution.map((item) => item.range) }, yAxis: { ...axis, type: "value" }, series: [{ type: "bar", data: summary.sentiment_distribution.map((item) => item.review_count), itemStyle: { color: "#60a5fa", borderRadius: [5, 5, 0, 0] } }] };
  const categories = [...new Set(summary.reviews.map((review) => review.category))];
  const scatter: EChartsOption = { ...base, tooltip: { trigger: "item", formatter: (params) => { const point = params as { data?: [number, number, string] }; return point.data ? `${point.data[2]}<br/>评分 ${point.data[0]} · 情绪 ${point.data[1]}` : ""; } }, legend: { data: categories, textStyle: { color: "#94a3b8" }, top: 0 }, xAxis: { ...axis, type: "value", name: "评分", min: 1, max: 5 }, yAxis: { ...axis, type: "value", name: "情绪", min: 0, max: 100 }, series: categories.map((category) => ({ name: category, type: "scatter", symbolSize: 9, data: summary.reviews.filter((review) => review.category === category).map((review) => [review.rating, review.sentiment, review.category]) })) };
  const keywordOption = (items: AnalyticsSummary["negative_keywords"], color: string): EChartsOption => ({ ...base, grid: { left: 90, right: 20, top: 12, bottom: 24 }, xAxis: { ...axis, type: "value" }, yAxis: { ...axis, type: "category", inverse: true, data: items.slice(0, 10).map((item) => item.keyword) }, series: [{ type: "bar", data: items.slice(0, 10).map((item) => item.weight), itemStyle: { color, borderRadius: [0, 5, 5, 0] } }] });
  const trend: EChartsOption = { ...base, legend: { data: ["平均情绪", "平均评分"], textStyle: { color: "#94a3b8" } }, xAxis: { ...axis, type: "category", data: summary.trend.map((item) => item.date) }, yAxis: [{ ...axis, type: "value", name: "情绪", min: 0, max: 100 }, { ...axis, type: "value", name: "评分", min: 0, max: 5 }], series: [{ name: "平均情绪", type: "line", smooth: true, data: summary.trend.map((item) => item.average_sentiment), lineStyle: { color: "#2dd4bf" }, itemStyle: { color: "#2dd4bf" }, areaStyle: { color: "rgba(45,212,191,.08)" } }, { name: "平均评分", type: "line", smooth: true, yAxisIndex: 1, data: summary.trend.map((item) => item.average_rating), lineStyle: { color: "#818cf8" }, itemStyle: { color: "#818cf8" } }] };

  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <Panel title="评分分布" eyebrow="Distribution"><Chart option={rating} label="评分分布图" /></Panel>
      <Panel title="情绪分布" eyebrow="Sentiment"><Chart option={sentiment} label="情绪分布图" /></Panel>
      <Panel title="评分 × 情绪" eyebrow="Correlation"><Chart option={scatter} label="评分情绪散点图" /><p className="mt-2 text-xs text-slate-600">散点使用后端摘要返回的最多 100 条预览数据。</p></Panel>
      <Panel title="舆情趋势" eyebrow="Timeline">{summary.trend.length ? <Chart option={trend} label="舆情趋势图" /> : <EmptyState title="暂无趋势数据" detail="CSV 中提供时间字段后可查看趋势。" />}</Panel>
      <Panel title="差评关键词" eyebrow="Negative signals">{summary.negative_keywords.length ? <Chart option={keywordOption(summary.negative_keywords, "#fb7185")} label="差评关键词图" /> : <EmptyState title="暂无差评关键词" detail="当前范围没有足够的差评文本。" />}</Panel>
      <Panel title="好评关键词" eyebrow="Positive signals">{summary.positive_keywords.length ? <Chart option={keywordOption(summary.positive_keywords, "#34d399")} label="好评关键词图" /> : <EmptyState title="暂无好评关键词" detail="当前范围没有足够的好评文本。" />}</Panel>
    </div>
  );
}
