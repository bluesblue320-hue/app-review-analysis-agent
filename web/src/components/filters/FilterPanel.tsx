import { RotateCcw, SlidersHorizontal } from "lucide-react";
import { useState } from "react";

import { DEFAULT_FILTERS, type Filters } from "../../types/api";

function initialDraft(filters: Filters, categories: string[]): Filters {
  if (categories.length === 0) return filters;
  const available = new Set(categories);
  return {
    ...filters,
    categories: filters.categories.filter((category) => available.has(category)),
  };
}

export function FilterPanel({
  filters,
  categories,
  onApply,
  disabled,
}: {
  filters: Filters;
  categories: string[];
  onApply: (filters: Filters) => void;
  disabled?: boolean;
}) {
  const [draft, setDraft] = useState(() => initialDraft(filters, categories));

  function update<K extends keyof Filters>(key: K, value: Filters[K]) {
    setDraft((current) => ({ ...current, [key]: value }));
  }

  function reset() {
    setDraft(DEFAULT_FILTERS);
    onApply(DEFAULT_FILTERS);
  }

  return (
    <form className="space-y-5" onSubmit={(event) => { event.preventDefault(); onApply(draft); }}>
      <fieldset disabled={disabled} className="space-y-5">
        <RangePair label="评分范围" min={1} max={5} low={draft.rating_min} high={draft.rating_max} onChange={(low, high) => setDraft({ ...draft, rating_min: low, rating_max: high })} />
        <RangePair label="情绪指数" min={0} max={100} low={draft.sentiment_min} high={draft.sentiment_max} onChange={(low, high) => setDraft({ ...draft, sentiment_min: low, sentiment_max: high })} />
        <label className="field-label">关键词
          <input className="field mt-2" value={draft.keyword} onChange={(event) => update("keyword", event.target.value)} placeholder="例如：封号、广告、客服" />
        </label>
        <div>
          <p className="field-label">问题类型</p>
          <div className="mt-2 max-h-40 space-y-2 overflow-auto pr-1">
            <label className="flex cursor-pointer items-center gap-2 text-sm text-slate-300">
              <input type="checkbox" className="accent-teal-400" checked={draft.categories.length === 0} onChange={() => update("categories", [])} />
              全部问题类型
            </label>
            {categories.length === 0 && <p className="pl-6 text-xs text-slate-600">当前数据集暂无可选类别</p>}
            {categories.map((category) => (
              <label key={category} className="flex cursor-pointer items-center gap-2 text-sm text-slate-400">
                <input type="checkbox" className="accent-teal-400" checked={draft.categories.includes(category)} onChange={(event) => {
                  const next = event.target.checked
                    ? [...draft.categories, category]
                    : draft.categories.filter((item) => item !== category);
                  update("categories", next);
                }} />
                {category}
              </label>
            ))}
          </div>
        </div>
        <label className="flex cursor-pointer items-center justify-between rounded-xl border border-slate-800 px-3 py-3 text-sm text-slate-300">
          只看高风险评论
          <input type="checkbox" className="h-4 w-4 accent-teal-400" checked={draft.high_risk_only} onChange={(event) => update("high_risk_only", event.target.checked)} />
        </label>
        <div className="grid grid-cols-2 gap-2">
          <button className="secondary-button" type="button" onClick={reset}><RotateCcw size={14} />重置</button>
          <button className="primary-button" type="submit"><SlidersHorizontal size={14} />应用筛选</button>
        </div>
      </fieldset>
    </form>
  );
}

function RangePair({ label, min, max, low, high, onChange }: { label: string; min: number; max: number; low: number; high: number; onChange: (low: number, high: number) => void }) {
  return (
    <div>
      <div className="flex items-center justify-between"><span className="field-label">{label}</span><span className="text-xs font-medium text-teal-300">{low} — {high}</span></div>
      <div className="mt-3 grid grid-cols-2 gap-2">
        <input aria-label={`${label}最小值`} className="field" type="number" min={min} max={high} value={low} onChange={(event) => onChange(Math.min(Number(event.target.value), high), high)} />
        <input aria-label={`${label}最大值`} className="field" type="number" min={low} max={max} value={high} onChange={(event) => onChange(low, Math.max(Number(event.target.value), low))} />
      </div>
    </div>
  );
}
