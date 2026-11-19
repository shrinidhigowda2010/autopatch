import { Navigate, Route, Routes } from "react-router-dom";
import Shell from "./components/Shell";
import Benchmark from "./pages/Benchmark";
import BugPage from "./pages/Bug";
import Dashboard from "./pages/Dashboard";
import DecisionLog from "./pages/DecisionLog";
import Explain from "./pages/Explain";
import Fix from "./pages/Fix";
import History from "./pages/History";
import Home from "./pages/Home";
import Login from "./pages/Login";
import MyHistory from "./pages/MyHistory";
import Profile from "./pages/Profile";
import Register from "./pages/Register";
import Scan from "./pages/Scan";
import TestPage from "./pages/Test";
import Assistant from "./pages/Assistant";
import Race from "./pages/Race";
import Upload from "./pages/Upload";

export default function App() {
  return (
    <Routes>
      <Route path="race" element={<Race />} />
      <Route element={<Shell />}>
        <Route index element={<Home />} />
        <Route path="login" element={<Login />} />
        <Route path="register" element={<Register />} />
        <Route path="profile" element={<Profile />} />
        <Route path="my-history" element={<MyHistory />} />
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
        <Route path="p/:projectId/decisions" element={<DecisionLog />} />
        <Route path="p/:projectId/assistant" element={<Assistant />} />
        <Route path="assistant" element={<Navigate to="/upload" replace />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
