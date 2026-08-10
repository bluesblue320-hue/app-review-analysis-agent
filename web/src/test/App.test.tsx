import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../components/charts/EChart", () => ({ EChart: ({ label }: { label: string }) => <div aria-label={label} /> }));

import App from "../App";
import { DatasetProvider, useDataset } from "../context/DatasetContext";
import { DEFAULT_FILTERS } from "../types/api";
import { agentResponse, dataset, datasetB, insightResponse, reviewPage, summary } from "./fixtures";

function json(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json", "X-Request-ID": "request-1" } });
}

function handler(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const url = String(input);
  if (init?.method === "DELETE" && url.includes("/datasets/")) return Promise.resolve(json({ dataset_id: dataset.dataset_id, deleted: true }));
  if (url.endsWith("/datasets")) return Promise.resolve(json(dataset, 201));
  if (url.endsWith("/analytics/summary")) return Promise.resolve(json(summary));
  if (url.endsWith("/analytics/reviews/search")) return Promise.resolve(json(reviewPage));
  if (url.endsWith("/ai/config")) return Promise.resolve(json({ provider: "deepseek", model: "test", configured: false }));
  if (url.endsWith("/ai/insights")) return Promise.resolve(json(insightResponse));
  if (url.endsWith("/agent/query")) return Promise.resolve(json(agentResponse));
  return Promise.resolve(json({ error: { code: "not_found", message: `No mock for ${url} ${init?.method}` }, request_id: "request-1" }, 404));
}

function configuredAIHandler(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  if (String(input).endsWith("/ai/config")) {
    return Promise.resolve(json({ provider: "deepseek", model: "test", configured: true }));
  }
  return handler(input, init);
}

function DatasetSwitcher() {
  const { setDataset } = useDataset();
  return <button onClick={() => setDataset({ metadata: datasetB, fileHash: "dataset-b-hash" })}>切换到数据集 B</button>;
}

function renderApp(withDataset = false, withSwitcher = false) {
  if (withDataset) sessionStorage.setItem("app-review-current-dataset", JSON.stringify({ metadata: dataset, fileHash: "abc" }));
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const rendered = render(
    <QueryClientProvider client={client}>
      <DatasetProvider>
        {withSwitcher && <DatasetSwitcher />}
        <App />
      </DatasetProvider>
    </QueryClientProvider>,
  );
  return { ...rendered, client };
}

function callsFor(path: string) {
  return vi.mocked(fetch).mock.calls.filter(([url]) => String(url).endsWith(path));
}

function lastSummaryPayload() {
  const call = callsFor("/analytics/summary").at(-1);
  return JSON.parse(String(call?.[1]?.body)) as { dataset_id: string; filters: typeof DEFAULT_FILTERS };
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
    expect(callsFor("/datasets")).toHaveLength(1);
  });

  it("commits draft filters only when Apply is clicked", async () => {
    const user = userEvent.setup();
    renderApp(true);
    await screen.findByText("评论洞察总览");
    const keyword = screen.getByPlaceholderText("例如：封号、广告、客服");
    await user.type(keyword, "封号");
    const before = callsFor("/analytics/summary").length;
    await user.click(screen.getByRole("button", { name: /应用筛选/ }));
    await waitFor(() => expect(callsFor("/analytics/summary").length).toBeGreaterThan(before));
    expect(lastSummaryPayload().filters.keyword).toBe("封号");
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
      const calls = callsFor("/analytics/reviews/search");
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
    expect(callsFor("/agent/query")).toHaveLength(1);
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

  it("resets filters, category draft and review pagination when the dataset changes", async () => {
    const user = userEvent.setup();
    renderApp(false, true);
    const file = new File(["评分,内容\n1,封号"], "dataset-a.csv", { type: "text/csv" });
    await user.upload(screen.getByLabelText("选择 CSV 文件"), file);
    await user.click(screen.getByRole("button", { name: "上传数据集" }));
    await screen.findByText("评论洞察总览");

    await user.type(screen.getByPlaceholderText("例如：封号、广告、客服"), "封号");
    await user.click(await screen.findByRole("checkbox", { name: "账号类" }));
    await user.click(screen.getByRole("button", { name: /应用筛选/ }));
    await waitFor(() => expect(lastSummaryPayload().filters.categories).toEqual(["账号类"]));
    await user.click(screen.getByRole("button", { name: "下一页" }));
    expect(await screen.findByText(/第 2 \/ 2 页/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "切换到数据集 B" }));
    await waitFor(() => expect(lastSummaryPayload()).toEqual({ dataset_id: datasetB.dataset_id, filters: DEFAULT_FILTERS }));
    expect(screen.getByPlaceholderText("例如：封号、广告、客服")).toHaveValue("");
    expect(screen.getByRole("checkbox", { name: "全部问题类型" })).toBeChecked();
    expect(await screen.findByRole("checkbox", { name: "账号类" })).not.toBeChecked();
    expect(await screen.findByText(/第 1 \/ 2 页/)).toBeInTheDocument();
  });

  it("clears an old AI insight when the dataset changes", async () => {
    const user = userEvent.setup();
    globalThis.fetch = vi.fn(configuredAIHandler);
    renderApp(true, true);
    await user.click(await screen.findByRole("button", { name: "生成 AI 洞察" }));
    expect(screen.getByText(/统计信息及部分评论样本/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "确认并生成" }));
    expect(await screen.findByText("旧数据集的 AI 洞察")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "切换到数据集 B" }));
    await screen.findByText("评论洞察总览");
    expect(screen.queryByText("旧数据集的 AI 洞察")).not.toBeInTheDocument();
  });

  it("represents the default category state as all categories with an empty payload", async () => {
    renderApp(true);
    expect(await screen.findByRole("checkbox", { name: "全部问题类型" })).toBeChecked();
    await waitFor(() => expect(callsFor("/analytics/summary").length).toBeGreaterThan(0));
    expect(lastSummaryPayload().filters.categories).toEqual([]);
  });

  it("submits only the specifically selected category", async () => {
    const user = userEvent.setup();
    renderApp(true);
    await user.click(await screen.findByRole("checkbox", { name: "账号类" }));
    expect(screen.getByRole("checkbox", { name: "全部问题类型" })).not.toBeChecked();
    await user.click(screen.getByRole("button", { name: /应用筛选/ }));
    await waitFor(() => expect(lastSummaryPayload().filters.categories).toEqual(["账号类"]));
  });

  it("restores all categories when filters are reset", async () => {
    const user = userEvent.setup();
    renderApp(true);
    await user.click(await screen.findByRole("checkbox", { name: "账号类" }));
    await user.click(screen.getByRole("button", { name: /应用筛选/ }));
    await waitFor(() => expect(lastSummaryPayload().filters.categories).toEqual(["账号类"]));

    await user.click(screen.getByRole("button", { name: /重置/ }));
    await waitFor(() => expect(lastSummaryPayload().filters.categories).toEqual([]));
    expect(screen.getByRole("checkbox", { name: "全部问题类型" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "账号类" })).not.toBeChecked();
  });

  it("clears dataset state, query cache, filters, insight and pagination on delete", async () => {
    const user = userEvent.setup();
    globalThis.fetch = vi.fn(configuredAIHandler);
    const { client } = renderApp(true);
    await screen.findByText("评论洞察总览");

    await user.type(screen.getByPlaceholderText("例如：封号、广告、客服"), "封号");
    await user.click(await screen.findByRole("checkbox", { name: "账号类" }));
    await user.click(screen.getByRole("button", { name: /应用筛选/ }));
    await waitFor(() => expect(lastSummaryPayload().filters.keyword).toBe("封号"));
    await user.click(screen.getByRole("button", { name: "下一页" }));
    expect(await screen.findByText(/第 2 \/ 2 页/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "生成 AI 洞察" }));
    await user.click(screen.getByRole("button", { name: "确认并生成" }));
    expect(await screen.findByText("旧数据集的 AI 洞察")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "移除数据集" }));
    expect(await screen.findByText("把用户评论转化为")).toBeInTheDocument();
    await waitFor(() => expect(client.getQueryCache().findAll({ predicate: (query) => JSON.stringify(query.queryKey).includes(dataset.dataset_id) })).toHaveLength(0));
    expect(screen.getByPlaceholderText("例如：封号、广告、客服")).toHaveValue("");
    expect(screen.getByRole("checkbox", { name: "全部问题类型" })).toBeChecked();
    expect(screen.queryByText("旧数据集的 AI 洞察")).not.toBeInTheDocument();
    expect(screen.queryByText("无故封号")).not.toBeInTheDocument();
    expect(screen.queryByText(/第 2 \/ 2 页/)).not.toBeInTheDocument();
  });
});
