import type { ReactNode } from "react";

export function Panel({
  title,
  eyebrow,
  action,
  children,
  className = "",
}: {
  title: string;
  eyebrow?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`panel ${className}`}>
      <header className="mb-5 flex items-start justify-between gap-4">
        <div>
          {eyebrow && <p className="eyebrow">{eyebrow}</p>}
          <h2 className="text-lg font-semibold text-slate-100">{title}</h2>
        </div>
        {action}
      </header>
      {children}
    </section>
  );
}

export function EmptyState({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="empty-state">
      <p className="font-medium text-slate-200">{title}</p>
      <p className="mt-1 text-sm text-slate-500">{detail}</p>
    </div>
  );
}

export function ErrorBanner({ message }: { message: string }) {
  return (
    <div className="rounded-xl border border-rose-400/25 bg-rose-400/10 px-4 py-3 text-sm text-rose-200" role="alert">
      {message}
    </div>
  );
}

export function Skeleton({ className = "h-24" }: { className?: string }) {
  return <div className={`animate-pulse rounded-xl bg-slate-800/70 ${className}`} aria-label="正在加载" />;
}

export function NoticeList({ items, tone = "amber" }: { items: string[]; tone?: "amber" | "blue" }) {
  if (!items.length) return null;
  const colors = tone === "amber" ? "border-amber-400/20 bg-amber-400/8 text-amber-100" : "border-blue-400/20 bg-blue-400/8 text-blue-100";
  return (
    <div className={`space-y-1 rounded-xl border px-4 py-3 text-sm ${colors}`}>
      {items.map((item) => <p key={item}>{item}</p>)}
    </div>
  );
}
