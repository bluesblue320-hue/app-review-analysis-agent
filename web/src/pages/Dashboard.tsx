import { useQuery } from "@tanstack/react-query";
import { Activity, Database, Menu, Sparkles } from "lucide-react";
import { useState } from "react";

import { getAnalyticsSummary } from "../api/analytics";
import { AgentPanel } from "../components/agent/AgentPanel";
import { AnalyticsCharts } from "../components/charts/AnalyticsCharts";
import { IssuePriority } from "../components/charts/IssuePriority";
import { ErrorBanner, NoticeList, Skeleton } from "../components/common/Panel";
import { FilterPanel } from "../components/filters/FilterPanel";
import { AIInsightPanel } from "../components/insights/AIInsightPanel";
import { KPICards } from "../components/metrics/KPICards";
import { ReviewPool } from "../components/reviews/ReviewPool";
import { DatasetUpload } from "../components/upload/DatasetUpload";
import { useDataset } from "../context/DatasetContext";
import { DEFAULT_FILTERS, type AIInsightResponse, type Filters } from "../types/api";
import { errorMessage } from "../utils/format";

export function Dashboard() {
  const { dataset } = useDataset();
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS);
  const [insight, setInsight] = useState<AIInsightResponse | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const datasetId = dataset?.metadata.dataset_id ?? "";
  const summary = useQuery({
    queryKey: ["summary", datasetId, filters, insight?.insight_id ?? null],
    queryFn: () => getAnalyticsSummary(datasetId, filters, insight?.insight_id),
    enabled: Boolean(datasetId),
  });

  function applyFilters(next: Filters) {
    setFilters(next);
    setInsight(null);
    setSidebarOpen(false);
  }

  return (
    <div className="min-h-screen">
      <header className="app-header">
        <div className="flex items-center gap-3"><div className="brand-mark"><Activity size={20} /></div><div><h1 className="text-base font-semibold tracking-tight text-white">App Review Intelligence</h1><p className="text-xs text-slate-500">Product signals · Controlled AI</p></div></div>
        <div className="flex items-center gap-3"><span className="hidden items-center gap-2 text-xs text-slate-500 sm:flex"><span className="h-2 w-2 rounded-full bg-emerald-400 shadow-[0_0_12px_#34d399]" />API connected via secure proxy</span><button className="icon-button lg:hidden" onClick={() => setSidebarOpen(!sidebarOpen)} aria-label="打开侧栏"><Menu size={18} /></button></div>
      </header>

      <div className="app-shell">
        <aside className={`sidebar ${sidebarOpen ? "open" : ""}`}>
          <div><div className="sidebar-title"><Database size={15} />数据集</div><DatasetUpload /></div>
          <div className="mt-7 border-t border-slate-800/80 pt-6"><div className="sidebar-title"><Sparkles size={15} />分析范围</div><FilterPanel filters={filters} categories={summary.data?.available_categories ?? []} onApply={applyFilters} disabled={!dataset} /></div>
          <p className="mt-8 text-[11px] leading-5 text-slate-700">筛选仅在点击“应用筛选”后提交。所有指标和 AI 范围都由后端重新计算。</p>
        </aside>

        <main className="main-content">
          {!dataset && <Welcome />}
          {dataset && summary.isLoading && <DashboardSkeleton />}
          {dataset && summary.error && <div className="mx-auto max-w-3xl py-24"><ErrorBanner message={errorMessage(summary.error)} /></div>}
          {dataset && summary.data && (
            <div className="space-y-5">
              <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-end"><div><p className="eyebrow">Live analytics workspace</p><h2 className="text-2xl font-semibold tracking-tight text-white">评论洞察总览</h2><p className="mt-1 text-sm text-slate-500">范围指纹 {summary.data.scope_signature.slice(0, 12)}… · {summary.data.sample_size} 条评论</p></div>{summary.isFetching && <span className="text-xs text-teal-300">正在刷新分析…</span>}</div>
              <NoticeList items={summary.data.warnings} />
              {summary.data.sample_size === 0 && <NoticeList items={["当前筛选范围没有评论，请放宽筛选条件。"]} />}
              <KPICards summary={summary.data} />
              <IssuePriority items={summary.data.issue_priorities} />
              <AnalyticsCharts summary={summary.data} />
              <ReviewPool key={JSON.stringify(filters)} datasetId={datasetId} filters={filters} />
              <AIInsightPanel datasetId={datasetId} filters={filters} scopeSignature={summary.data.scope_signature} insight={insight} onInsight={setInsight} />
              <AgentPanel datasetId={datasetId} filters={filters} insightId={insight?.scope_signature === summary.data.scope_signature ? insight.insight_id : undefined} />
            </div>
          )}
        </main>
      </div>
      {sidebarOpen && <button className="fixed inset-0 z-30 bg-black/60 lg:hidden" aria-label="关闭侧栏" onClick={() => setSidebarOpen(false)} />}
    </div>
  );
}

function Welcome() {
  return <div className="welcome"><div className="brand-mark mx-auto h-12 w-12"><Activity size={24} /></div><p className="eyebrow mt-6">Review intelligence platform</p><h2 className="mt-2 text-3xl font-semibold tracking-tight text-white sm:text-4xl">把用户评论转化为<br /><span className="text-gradient">清晰、可行动的产品信号</span></h2><p className="mx-auto mt-5 max-w-xl text-sm leading-7 text-slate-500">上传 CSV 后，后端将完成清洗、情绪分析、风险识别和问题优先级计算。React 前端只负责安全地呈现与交互。</p><div className="mx-auto mt-8 grid max-w-2xl gap-3 sm:grid-cols-3"><WelcomeItem number="01" title="上传评论" detail="评分 + 内容" /><WelcomeItem number="02" title="探索信号" detail="筛选 + 可视化" /><WelcomeItem number="03" title="深度分析" detail="AI + Agent" /></div><p className="mt-8 text-xs text-slate-600">从左侧上传 CSV 开始</p></div>;
}

function WelcomeItem({ number, title, detail }: { number: string; title: string; detail: string }) { return <div className="rounded-2xl border border-slate-800 bg-slate-900/35 p-4 text-left"><span className="text-xs font-semibold text-teal-400">{number}</span><p className="mt-3 text-sm font-medium text-slate-200">{title}</p><p className="mt-1 text-xs text-slate-600">{detail}</p></div>; }
function DashboardSkeleton() { return <div className="space-y-5"><Skeleton className="h-16" /><div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">{Array.from({ length: 5 }, (_, index) => <Skeleton className="h-32" key={index} />)}</div><Skeleton className="h-96" /><div className="grid gap-4 xl:grid-cols-2"><Skeleton className="h-96" /><Skeleton className="h-96" /></div></div>; }
