import { Navigate, Route, Routes } from "react-router-dom";
import Shell from "./components/Shell";
import Benchmark from "./pages/Benchmark";
import BugPage from "./pages/Bug";
import Dashboard from "./pages/Dashboard";
import Explain from "./pages/Explain";
import Fix from "./pages/Fix";
import History from "./pages/History";
import Home from "./pages/Home";
import Scan from "./pages/Scan";
import TestPage from "./pages/Test";
import Upload from "./pages/Upload";

export default function App() {
  return (
    <Routes>
      <Route element={<Shell />}>
        <Route index element={<Home />} />
        <Route path="upload" element={<Upload />} />
        <Route path="benchmark" element={<Benchmark />} />
        <Route path="p/:projectId/upload" element={<Upload />} />
        <Route path="p/:projectId/scan" element={<Scan />} />
        <Route path="p/:projectId/explain" element={<Explain />} />
        <Route path="p/:projectId/explain/:bugId" element={<BugPage />} />
        <Route path="p/:projectId/fix" element={<Fix />} />
        <Route path="p/:projectId/test" element={<TestPage />} />
        <Route path="p/:projectId/dashboard" element={<Dashboard />} />
        <Route path="p/:projectId/history" element={<History />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
