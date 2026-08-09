import { AlertTriangle, MessageSquareText, ShieldCheck, Star, TrendingDown } from "lucide-react";
import type { ComponentType } from "react";

import type { AnalyticsSummary } from "../../types/api";
import { formatNumber } from "../../utils/format";

export function KPICards({ summary }: { summary: AnalyticsSummary }) {
  const health = summary.average_sentiment > 60 ? "健康" : summary.average_sentiment > 40 ? "需警惕" : "高风险";
  const cards: Array<{ label: string; value: string; detail?: string; icon: ComponentType<{ size?: number }> }> = [
    { label: "评论数", value: formatNumber(summary.sample_size, 0), icon: MessageSquareText },
    { label: "平均星级", value: summary.average_rating.toFixed(2), icon: Star },
    { label: "差评占比", value: `${summary.negative_ratio.toFixed(1)}%`, icon: TrendingDown },
    { label: "平均情绪", value: summary.average_sentiment.toFixed(1), detail: health, icon: ShieldCheck },
    { label: "高风险评论", value: formatNumber(summary.high_risk_count, 0), icon: AlertTriangle },
  ];
  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
      {cards.map(({ label, value, detail, icon: Icon }) => (
        <article className="metric-card" key={label}>
          <div className="flex items-center justify-between"><span className="text-sm text-slate-500">{label}</span><Icon size={17} /></div>
          <div className="mt-4 flex items-end justify-between"><strong className="text-2xl font-semibold text-white">{value}</strong>{detail && <span className="status-pill">{detail}</span>}</div>
        </article>
      ))}
    </div>
  );
}
