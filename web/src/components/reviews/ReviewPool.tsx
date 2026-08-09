import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { useState } from "react";

import { searchReviews } from "../../api/reviews";
import type { Filters, ReviewView } from "../../types/api";
import { errorMessage } from "../../utils/format";
import { EmptyState, ErrorBanner, Panel, Skeleton } from "../common/Panel";

const PAGE_SIZE = 20;

export function ReviewPool({ datasetId, filters }: { datasetId: string; filters: Filters }) {
  const [offset, setOffset] = useState(0);
  const [view, setView] = useState<ReviewView>("all");
  const query = useQuery({
    queryKey: ["reviews", datasetId, filters, view, offset],
    queryFn: () => searchReviews(datasetId, filters, view, offset, PAGE_SIZE),
    placeholderData: keepPreviousData,
  });
  const page = query.data;
  const pageNumber = Math.floor(offset / PAGE_SIZE) + 1;
  const totalPages = page ? Math.max(1, Math.ceil(page.total / PAGE_SIZE)) : 1;
  return (
    <Panel title="评论池" eyebrow="Server-side pagination" action={<select className="field w-auto" aria-label="评论视图" value={view} onChange={(event) => { setView(event.target.value as ReviewView); setOffset(0); }}><option value="all">全部评论</option><option value="high_risk">高风险</option><option value="rating_sentiment_mismatch">高星低情绪</option></select>}>
      {query.isLoading && <Skeleton className="h-64" />}
      {query.error && <ErrorBanner message={errorMessage(query.error)} />}
      {page && page.items.length === 0 && <EmptyState title="没有匹配评论" detail="尝试放宽筛选条件或切换评论视图。" />}
      {page && page.items.length > 0 && (
        <>
          <div className="space-y-3">
            {page.items.map((review, index) => (
              <article className="review-card" key={`${offset}-${index}-${review.content.slice(0, 12)}`}>
                <div className="flex flex-wrap items-center gap-2 text-xs"><span className="rating-badge">{review.rating.toFixed(1)} 星</span><span className="tag">情绪 {review.sentiment.toFixed(1)}</span><span className="tag">{review.category}</span><span className="tag">{review.risk_label}</span>{review.version && <span className="tag">v{review.version}</span>}</div>
                <p className="mt-3 text-sm leading-6 text-slate-300">{review.content}</p>
              </article>
            ))}
          </div>
          <footer className="mt-5 flex items-center justify-between border-t border-slate-800 pt-4 text-sm text-slate-500">
            <span>第 {pageNumber} / {totalPages} 页 · 共 {page.total} 条</span>
            <div className="flex gap-2"><button className="secondary-button" aria-label="上一页" disabled={offset === 0 || query.isFetching} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}><ChevronLeft size={15} />上一页</button><button className="secondary-button" aria-label="下一页" disabled={page.next_offset === null || query.isFetching} onClick={() => page.next_offset !== null && setOffset(page.next_offset)} >下一页<ChevronRight size={15} /></button></div>
          </footer>
        </>
      )}
    </Panel>
  );
}
