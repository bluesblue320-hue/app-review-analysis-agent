import { createContext, useContext, useMemo, useState, type ReactNode } from "react";

import type { DatasetUploadResponse } from "../types/api";

interface StoredDataset {
  metadata: DatasetUploadResponse;
  fileHash: string;
}

interface DatasetContextValue {
  dataset: StoredDataset | null;
  setDataset: (dataset: StoredDataset | null) => void;
}

const STORAGE_KEY = "app-review-current-dataset";
const DatasetContext = createContext<DatasetContextValue | null>(null);

function restoreDataset(): StoredDataset | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as StoredDataset) : null;
  } catch {
    sessionStorage.removeItem(STORAGE_KEY);
    return null;
  }
}

export function DatasetProvider({ children }: { children: ReactNode }) {
  const [dataset, setDatasetState] = useState<StoredDataset | null>(restoreDataset);
  const value = useMemo<DatasetContextValue>(
    () => ({
      dataset,
      setDataset(next) {
        setDatasetState(next);
        if (next) sessionStorage.setItem(STORAGE_KEY, JSON.stringify(next));
        else sessionStorage.removeItem(STORAGE_KEY);
      },
    }),
    [dataset],
  );
  return <DatasetContext.Provider value={value}>{children}</DatasetContext.Provider>;
}

export function useDataset() {
  const context = useContext(DatasetContext);
  if (!context) throw new Error("useDataset must be used inside DatasetProvider");
  return context;
}
