import { useMutation } from "@tanstack/react-query";
import { Bot, CheckCircle2, ChevronDown, CircleDashed, Send, UserRound, XCircle } from "lucide-react";
import { useState } from "react";

import { queryAgent } from "../../api/agent";
import type { AgentQueryResponse, Filters, ToolCall } from "../../types/api";
import { cellText, errorMessage } from "../../utils/format";
import { ErrorBanner, NoticeList, Panel } from "../common/Panel";

type ChatMessage = { id: string; question: string; response: AgentQueryResponse };

export function AgentPanel({ datasetId, filters, insightId }: { datasetId: string; filters: Filters; insightId?: string }) {
  const [question, setQuestion] = useState("");
  const [scope, setScope] = useState<"full" | "filtered">("filtered");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const mutation = useMutation({
    mutationFn: (text: string) => queryAgent({ dataset_id: datasetId, question: text, filters, scope, ...(insightId ? { insight_id: insightId } : {}) }),
    onSuccess: (response, text) => { setMessages((current) => [...current, { id: crypto.randomUUID(), question: text, response }]); setQuestion(""); },
  });

  function submit() {
    const normalized = question.trim();
    if (normalized && !mutation.isPending) mutation.mutate(normalized);
  }

  return (
    <Panel title="Agent 分析" eyebrow="Controlled tool calling" action={<div className="segmented"><button className={scope === "filtered" ? "active" : ""} onClick={() => setScope("filtered")}>当前筛选</button><button className={scope === "full" ? "active" : ""} onClick={() => setScope("full")}>完整数据</button></div>}>
      <div className="space-y-5">
        {messages.length === 0 && <div className="rounded-2xl border border-dashed border-slate-700 p-5"><div className="flex items-center gap-2 text-slate-300"><Bot size={18} className="text-indigo-300" /><span className="font-medium">向分析 Agent 提问</span></div><div className="mt-3 flex flex-wrap gap-2">{["差评主要集中在哪些问题？", "哪些评论需要人工优先处理？", "最近评分趋势有没有下降？"].map((prompt) => <button className="prompt-chip" onClick={() => setQuestion(prompt)} key={prompt}>{prompt}</button>)}</div></div>}
        {messages.map((message) => <AgentMessage message={message} key={message.id} />)}
        {mutation.isPending && <div className="flex items-center gap-3 rounded-xl bg-indigo-400/5 px-4 py-4 text-sm text-indigo-200"><CircleDashed className="animate-spin" size={18} />Agent 正在规划并执行分析工具…</div>}
        {mutation.error && <ErrorBanner message={errorMessage(mutation.error)} />}
        <div className="rounded-2xl border border-slate-700 bg-slate-950/55 p-2 focus-within:border-teal-400/50"><textarea className="min-h-24 w-full resize-none bg-transparent px-3 py-2 text-sm text-slate-200 outline-none placeholder:text-slate-600" aria-label="Agent 问题" placeholder="例如：为什么 4.2.1 版本差评增加？" value={question} onChange={(event) => setQuestion(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); submit(); } }} disabled={mutation.isPending} /><div className="flex items-center justify-between px-2 pb-1"><span className="text-xs text-slate-600">Enter 发送 · Shift + Enter 换行</span><button className="primary-button" onClick={submit} disabled={!question.trim() || mutation.isPending}><Send size={15} />发送</button></div></div>
      </div>
    </Panel>
  );
}

function AgentMessage({ message }: { message: ChatMessage }) {
  const { response } = message;
  return (
    <article className="space-y-3">
      <div className="flex justify-end"><div className="max-w-2xl rounded-2xl rounded-tr-sm bg-teal-400/10 px-4 py-3 text-sm text-teal-50"><div className="mb-1 flex items-center justify-end gap-1 text-xs text-teal-300"><UserRound size={12} />你的问题</div>{message.question}</div></div>
      <div className="rounded-2xl border border-indigo-400/15 bg-indigo-400/5 p-5"><div className="mb-3 flex flex-wrap items-center gap-2"><Bot size={17} className="text-indigo-300" /><span className="text-xs font-semibold uppercase tracking-widest text-indigo-300">Agent answer</span><span className="tag">{response.sample_size} 条样本</span></div><div className="whitespace-pre-wrap text-sm leading-7 text-slate-200">{response.answer}</div></div>
      <details className="details-panel"><summary><span>Routing</span><ChevronDown size={15} /></summary><div className="detail-grid"><KeyValue label="意图" value={response.intent} /><KeyValue label="路由" value={response.routing} /><KeyValue label="范围" value={response.scope_label} /><KeyValue label="范围指纹" value={response.scope_signature} /></div></details>
      <details className="details-panel" open={response.tool_calls.length > 0}><summary><span>Tool Calls ({response.tool_calls.length})</span><ChevronDown size={15} /></summary><div className="space-y-3">{response.tool_calls.length ? response.tool_calls.map((call, index) => <ToolCallView call={call} index={index} key={`${call.name}-${index}`} />) : <p className="text-sm text-slate-500">此回答由规则快速路由生成，没有工具调用记录。</p>}</div></details>
      {response.evidence_call_ids.length > 0 && <details className="details-panel"><summary><span>Evidence ({response.evidence_call_ids.length})</span><ChevronDown size={15} /></summary><div className="flex flex-wrap gap-2">{response.evidence_call_ids.map((id) => <code className="tag" key={id}>{id}</code>)}</div>{Object.keys(response.evidence).length > 0 && <pre className="json-block">{JSON.stringify(response.evidence, null, 2)}</pre>}</details>}
      {Object.entries(response.tables).map(([name, records]) => <ResultTable name={name} records={records} key={name} />)}
      <NoticeList items={response.warnings} />
      <NoticeList items={response.limitations} tone="blue" />
    </article>
  );
}

function ToolCallView({ call, index }: { call: ToolCall; index: number }) {
  const Icon = call.status === "success" ? CheckCircle2 : call.status === "failed" ? XCircle : ShieldIcon;
  return <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-4"><div className="flex items-center gap-2"><Icon size={16} className={call.status === "success" ? "text-emerald-400" : "text-rose-400"} /><strong className="text-sm text-slate-200">{index + 1}. {call.name}</strong><span className="tag ml-auto">{call.status} · {call.duration_ms} ms</span></div><pre className="json-block">{JSON.stringify(call.arguments, null, 2)}</pre>{call.error && <p className="mt-2 text-sm text-rose-300">{call.error}</p>}</div>;
}

function ShieldIcon(props: { size?: number; className?: string }) { return <XCircle {...props} />; }
function KeyValue({ label, value }: { label: string; value: string }) { return <div><dt className="text-xs text-slate-600">{label}</dt><dd className="mt-1 break-all text-sm text-slate-300">{value}</dd></div>; }

function ResultTable({ name, records }: { name: string; records: Array<Record<string, unknown>> }) {
  if (!records.length) return null;
  const columns = Object.keys(records[0]);
  return <details className="details-panel"><summary><span>{name} ({records.length})</span><ChevronDown size={15} /></summary><div className="table-wrap"><table><thead><tr>{columns.map((column) => <th key={column}>{column}</th>)}</tr></thead><tbody>{records.map((record, index) => <tr key={index}>{columns.map((column) => <td key={column}>{cellText(record[column])}</td>)}</tr>)}</tbody></table></div></details>;
}
