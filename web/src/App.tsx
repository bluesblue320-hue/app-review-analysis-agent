import { Dashboard } from "./pages/Dashboard";
import { useDataset } from "./context/DatasetContext";

export default function App() {
  const { dataset } = useDataset();
  const datasetId = dataset?.metadata.dataset_id ?? "welcome";

  return <Dashboard key={datasetId} />;
}
