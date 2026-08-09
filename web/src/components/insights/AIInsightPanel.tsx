import { useMutation, useQuery } from "@tanstack/react-query";
import { BrainCircuit, Check, ShieldAlert } from "lucide-react";
import { useEffect, useState } from "react";

import { generateAIInsight, getAIConfig } from "../../api/insights";
import type { AIInsightResponse, Filters } from "../../types/api";
import { errorMessage } from "../../utils/format";
import { EmptyState, ErrorBanner, NoticeList, Panel, Skeleton } from "../common/Panel";

const CONSENT_KEY = "ai-consent-confirmed";

function field(item: Record<string, unknown>, key: string): string {
  const value = item[key];
  return typeof value === "string" ? value : "";
}

function listField(item: Record<string, unknown>, key: string): string[] {
  const value = item[key];
  return Array.isArray(value) ? value.filter((entry): entry is string => typeof entry === "string") : [];
}

export function AIInsightPanel({
  datasetId,
  filters,
  scopeSignature,
  insight,
  onInsight,
}: {
  datasetId: string;
  filters: Filters;
  scopeSignature: string;
  insight: AIInsightResponse | null;
  onInsight: (insight: AIInsightResponse | null) => void;
}) {
  const config = useQuery({ queryKey: ["ai-config"], queryFn: getAIConfig, staleTime: 60_000 });
  const [showConsent, setShowConsent] = useState(false);
  const generate = useMutation({
    mutationFn: () => generateAIInsight(datasetId, filters),
    onSuccess: onInsight,
  });
  useEffect(() => {
    if (insight && insight.scope_signature !== scopeSignature) onInsight(null);
  }, [insight, onInsight, scopeSignature]);

  function start() {
    if (sessionStorage.getItem(CONSENT_KEY) === "true") generate.mutate();
    else setShowConsent(true);
  }

  function confirm() {
    sessionStorage.setItem(CONSENT_KEY, "true");
    setShowConsent(false);
    generate.mutate();
  }

  const currentInsight = insight?.scope_signature === scopeSignature ? insight : null;
  const content = currentInsight?.insights;
  return (
    <Panel title="AI 舆情洞察" eyebrow="Model-assisted synthesis" action={config.data && <span className={`status-pill ${config.data.configured ? "text-emerald-300" : "text-amber-300"}`}>{config.data.provider} / {config.data.model}</span>}>
      {config.isLoading && <Skeleton className="h-20" />}
      {config.error && <ErrorBanner message={errorMessage(config.error)} />}
      {config.data && !config.data.configured && <NoticeList items={["后端未配置模型密钥。确定性看板和规则 Agent 仍可正常使用。"]} />}
      {showConsent && (
        <div className="mb-4 rounded-2xl border border-amber-400/25 bg-amber-400/8 p-4">
          <div className="flex gap-3"><ShieldAlert className="mt-0.5 shrink-0 text-amber-300" size={20} /><div><p className="font-medium text-amber-100">确认发送分析摘要</p><p className="mt-1 text-sm leading-6 text-amber-100/70">当前筛选范围内的评论摘要将发送给外部大模型。此确认只在当前浏览器会话中有效。</p></div></div>
          <div className="mt-4 flex justify-end gap-2"><button className="secondary-button" onClick={() => setShowConsent(false)}>取消</button><button className="primary-button" onClick={confirm}>确认并生成</button></div>
        </div>
      )}
      {generate.error && <ErrorBanner message={errorMessage(generate.error)} />}
      {!content && !generate.isPending && config.data?.configured && (
        <EmptyState title="尚未生成当前范围的 AI 洞察" detail="生成结果会与当前数据集和筛选范围指纹绑定。" />
      )}
      {generate.isPending && <div className="space-y-3"><Skeleton className="h-24" /><Skeleton className="h-36" /></div>}
      {content && (
        <div className="space-y-6">
          <div className="rounded-2xl border border-indigo-400/15 bg-indigo-400/5 p-5"><div className="mb-2 flex items-center gap-2 text-indigo-300"><BrainCircuit size={18} /><span className="text-xs font-semibold uppercase tracking-widest">Executive summary</span></div><p className="leading-7 text-slate-200">{content.summary || "暂无总览。"}</p></div>
          <InsightItems title="核心槽点" items={content.pain_points} />
          <InsightItems title="核心爽点" items={content.delighters} />
          {content.sentiment_drivers && content.sentiment_drivers.length > 0 && <InsightList title="情绪归因" items={content.sentiment_drivers} />}
          {content.recommendations && content.recommendations.length > 0 && <InsightList title="产品与运营建议" items={content.recommendations} />}
          {content.report_copy && <div><h3 className="subheading">可复制汇报文案</h3><div className="mt-3 whitespace-pre-wrap rounded-xl bg-slate-950/60 p-4 text-sm leading-6 text-slate-300">{content.report_copy}</div></div>}
        </div>
      )}
      <div className="mt-5 flex justify-end"><button className="primary-button" onClick={start} disabled={!config.data?.configured || generate.isPending}><BrainCircuit size={16} />{currentInsight ? "重新生成" : "生成 AI 洞察"}</button></div>
    </Panel>
  );
}

function InsightItems({ title, items }: { title: string; items?: Array<Record<string, unknown> | string> }) {
  if (!items?.length) return null;
  return <div><h3 className="subheading">{title}</h3><div className="mt-3 grid gap-3 md:grid-cols-2">{items.map((raw, index) => { const item = typeof raw === "string" ? { name: raw } : raw; return <article className="rounded-xl border border-slate-800 bg-slate-950/35 p-4" key={`${field(item, "name")}-${index}`}><div className="flex items-center gap-2"><span className="flex h-5 w-5 items-center justify-center rounded-full bg-teal-400/10 text-teal-300"><Check size={12} /></span><strong className="text-sm text-slate-200">{field(item, "name") || `${title} ${index + 1}`}</strong>{field(item, "severity") && <span className="tag">{field(item, "severity")}</span>}</div>{field(item, "explanation") && <p className="mt-3 text-sm leading-6 text-slate-400">{field(item, "explanation")}</p>}{listField(item, "evidence").map((quote) => <p key={quote} className="mt-2 border-l border-slate-700 pl-3 text-xs text-slate-500">{quote}</p>)}{field(item, "suggestion") && <p className="mt-3 text-sm text-teal-200/80">建议：{field(item, "suggestion")}</p>}</article>; })}</div></div>;
}

function InsightList({ title, items }: { title: string; items: string[] }) {
  return <div><h3 className="subheading">{title}</h3><ul className="mt-3 space-y-2">{items.map((item) => <li className="flex gap-2 text-sm leading-6 text-slate-400" key={item}><Check className="mt-1 shrink-0 text-teal-400" size={14} />{item}</li>)}</ul></div>;
}
