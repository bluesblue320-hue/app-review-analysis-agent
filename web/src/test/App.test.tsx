import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../components/charts/EChart", () => ({ EChart: ({ label }: { label: string }) => <div aria-label={label} /> }));

import App from "../App";
import { DatasetProvider } from "../context/DatasetContext";
import { agentResponse, dataset, reviewPage, summary } from "./fixtures";

function json(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json", "X-Request-ID": "request-1" } });
}

function handler(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const url = String(input);
  if (url.endsWith("/datasets")) return Promise.resolve(json(dataset, 201));
  if (url.endsWith("/analytics/summary")) return Promise.resolve(json(summary));
  if (url.endsWith("/analytics/reviews/search")) return Promise.resolve(json(reviewPage));
  if (url.endsWith("/ai/config")) return Promise.resolve(json({ provider: "deepseek", model: "test", configured: false }));
  if (url.endsWith("/agent/query")) return Promise.resolve(json(agentResponse));
  return Promise.resolve(json({ error: { code: "not_found", message: `No mock for ${url} ${init?.method}` }, request_id: "request-1" }, 404));
}

function renderApp(withDataset = false) {
  if (withDataset) sessionStorage.setItem("app-review-current-dataset", JSON.stringify({ metadata: dataset, fileHash: "abc" }));
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={client}><DatasetProvider><App /></DatasetProvider></QueryClientProvider>);
}

beforeEach(() => { globalThis.fetch = vi.fn(handler); });
afterEach(() => { cleanup(); sessionStorage.clear(); vi.restoreAllMocks(); });

describe("Dashboard core paths", () => {
  it("renders the dashboard welcome state", () => {
    renderApp();
    expect(screen.getByText("把用户评论转化为")).toBeInTheDocument();
    expect(screen.getByText("上传评论")).toBeInTheDocument();
  });

  it("uploads a CSV once and renders the dashboard", async () => {
    const user = userEvent.setup();
    renderApp();
    const file = new File(["评分,内容\n5,很好"], "reviews.csv", { type: "text/csv" });
    await user.upload(screen.getByLabelText("选择 CSV 文件"), file);
    await user.click(screen.getByRole("button", { name: "上传数据集" }));
    expect(await screen.findByText("数据集已就绪")).toBeInTheDocument();
    expect(await screen.findByText("评论洞察总览")).toBeInTheDocument();
    expect(vi.mocked(fetch).mock.calls.filter(([url]) => String(url).endsWith("/datasets"))).toHaveLength(1);
  });

  it("commits draft filters only when Apply is clicked", async () => {
    const user = userEvent.setup();
    renderApp(true);
    await screen.findByText("评论洞察总览");
    const keyword = screen.getByPlaceholderText("例如：封号、广告、客服");
    await user.type(keyword, "封号");
    const before = vi.mocked(fetch).mock.calls.filter(([url]) => String(url).endsWith("/analytics/summary")).length;
    await user.click(screen.getByRole("button", { name: /应用筛选/ }));
    await waitFor(() => expect(vi.mocked(fetch).mock.calls.filter(([url]) => String(url).endsWith("/analytics/summary")).length).toBeGreaterThan(before));
    const calls = vi.mocked(fetch).mock.calls.filter(([url]) => String(url).endsWith("/analytics/summary"));
    const payload = JSON.parse(String(calls.at(-1)?.[1]?.body)) as { filters: { keyword: string } };
    expect(payload.filters.keyword).toBe("封号");
  });

  it("shows a typed API error", async () => {
    globalThis.fetch = vi.fn((input: RequestInfo | URL, init?: RequestInit) => String(input).endsWith("/analytics/summary") ? Promise.resolve(json({ error: { code: "validation_error", message: "筛选范围无效" }, request_id: "req-error" }, 422)) : handler(input, init));
    renderApp(true);
    expect(await screen.findByText(/筛选范围无效/)).toBeInTheDocument();
    expect(screen.getByText(/req-error/)).toBeInTheDocument();
  });

  it("uses server pagination for the next review page", async () => {
    const user = userEvent.setup();
    renderApp(true);
    await screen.findByText("无故封号");
    await user.click(screen.getByRole("button", { name: "下一页" }));
    await waitFor(() => {
      const calls = vi.mocked(fetch).mock.calls.filter(([url]) => String(url).endsWith("/analytics/reviews/search"));
      const payload = JSON.parse(String(calls.at(-1)?.[1]?.body)) as { offset: number };
      expect(payload.offset).toBe(20);
    });
  });

  it("submits an Agent question and prevents duplicate submission", async () => {
    const user = userEvent.setup();
    renderApp(true);
    const input = await screen.findByLabelText("Agent 问题");
    await user.type(input, "为什么 4.2.1 版本差评增加？");
    const submit = screen.getByRole("button", { name: "发送" });
    await user.click(submit);
    expect(await screen.findByText("4.2.1 版本的账号类问题增加。")).toBeInTheDocument();
    expect(vi.mocked(fetch).mock.calls.filter(([url]) => String(url).endsWith("/agent/query"))).toHaveLength(1);
  });

  it("renders Agent routing, tools, evidence, warnings and limitations", async () => {
    const user = userEvent.setup();
    renderApp(true);
    await user.type(await screen.findByLabelText("Agent 问题"), "分析版本问题");
    await user.click(screen.getByRole("button", { name: "发送" }));
    expect(await screen.findByText(/version_compare/)).toBeInTheDocument();
    expect(screen.getByText("call_1")).toBeInTheDocument();
    expect(screen.getByText("样本量较小。")).toBeInTheDocument();
    expect(screen.getByText("仅基于上传评论。")).toBeInTheDocument();
    expect(screen.getByText("tool_calling")).toBeInTheDocument();
  });
});
