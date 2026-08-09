import { useMutation, useQueryClient } from "@tanstack/react-query";
import { FileSpreadsheet, UploadCloud, X } from "lucide-react";
import { useRef, useState, type DragEvent } from "react";

import { deleteDataset, uploadDataset } from "../../api/datasets";
import { useDataset } from "../../context/DatasetContext";
import { errorMessage } from "../../utils/format";
import { ErrorBanner } from "../common/Panel";

async function hashFile(file: File): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

export function DatasetUpload() {
  const inputRef = useRef<HTMLInputElement>(null);
  const queryClient = useQueryClient();
  const { dataset, setDataset } = useDataset();
  const [selected, setSelected] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [clientError, setClientError] = useState("");
  const upload = useMutation({
    mutationFn: async (file: File) => {
      const fileHash = await hashFile(file);
      if (dataset?.fileHash === fileHash) throw new Error("这个文件已经上传，无需重复提交。");
      return { metadata: await uploadDataset(file), fileHash };
    },
    onSuccess: (next) => {
      setDataset(next);
      setSelected(null);
      void queryClient.invalidateQueries();
    },
  });
  const remove = useMutation({
    mutationFn: () => deleteDataset(dataset!.metadata.dataset_id),
    onSettled: () => {
      setDataset(null);
      queryClient.clear();
    },
  });

  function choose(file?: File) {
    setClientError("");
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".csv")) {
      setClientError("仅支持 CSV 文件。");
      return;
    }
    setSelected(file);
  }

  function drop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    choose(event.dataTransfer.files[0]);
  }

  if (dataset) {
    const { metadata } = dataset;
    return (
      <div className="rounded-2xl border border-teal-400/20 bg-teal-400/6 p-4">
        <div className="flex items-center gap-3">
          <span className="rounded-xl bg-teal-400/10 p-2 text-teal-300"><FileSpreadsheet size={20} /></span>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium text-slate-100">数据集已就绪</p>
            <p className="truncate text-xs text-slate-500" title={metadata.dataset_id}>{metadata.dataset_id}</p>
          </div>
          <button className="icon-button" onClick={() => remove.mutate()} aria-label="移除数据集" disabled={remove.isPending}><X size={16} /></button>
        </div>
        <div className="mt-4 grid grid-cols-2 gap-2 text-xs">
          <div className="stat-mini"><span>有效评论</span><strong>{metadata.valid_rows}</strong></div>
          <div className="stat-mini"><span>已移除</span><strong>{metadata.removed_rows}</strong></div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div
        className={`upload-zone ${dragging ? "border-teal-300 bg-teal-300/8" : ""}`}
        onDragOver={(event) => { event.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={drop}
        onClick={() => inputRef.current?.click()}
        role="button"
        tabIndex={0}
        onKeyDown={(event) => event.key === "Enter" && inputRef.current?.click()}
      >
        <UploadCloud className="mx-auto text-teal-300" size={26} />
        <p className="mt-3 text-sm font-medium text-slate-200">拖放 CSV 或点击选择</p>
        <p className="mt-1 text-xs text-slate-500">需包含“评分”和“内容”列</p>
        <input ref={inputRef} className="hidden" type="file" accept=".csv,text/csv" onChange={(event) => choose(event.target.files?.[0])} aria-label="选择 CSV 文件" />
      </div>
      {selected && (
        <div className="rounded-xl border border-slate-700 bg-slate-900/50 p-3 text-sm">
          <p className="truncate text-slate-200">{selected.name}</p>
          <p className="mt-1 text-xs text-slate-500">{(selected.size / 1024).toFixed(1)} KB</p>
          <button className="primary-button mt-3 w-full" onClick={() => upload.mutate(selected)} disabled={upload.isPending}>
            {upload.isPending ? "上传并分析中…" : "上传数据集"}
          </button>
        </div>
      )}
      {(clientError || upload.error) && <ErrorBanner message={clientError || errorMessage(upload.error)} />}
    </div>
  );
}
