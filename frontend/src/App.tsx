import { Suspense, lazy } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import Shell from "./components/Shell";
import Home from "./pages/Home";

// Home loads with the app; every other page is fetched when first opened.
const Assistant = lazy(() => import("./pages/Assistant"));
const Benchmark = lazy(() => import("./pages/Benchmark"));
const BugPage = lazy(() => import("./pages/Bug"));
const Dashboard = lazy(() => import("./pages/Dashboard"));
const DecisionLog = lazy(() => import("./pages/DecisionLog"));
const Explain = lazy(() => import("./pages/Explain"));
const Fix = lazy(() => import("./pages/Fix"));
const History = lazy(() => import("./pages/History"));
const Login = lazy(() => import("./pages/Login"));
const MyHistory = lazy(() => import("./pages/MyHistory"));
const Profile = lazy(() => import("./pages/Profile"));
const Race = lazy(() => import("./pages/Race"));
const Register = lazy(() => import("./pages/Register"));
const Scan = lazy(() => import("./pages/Scan"));
const TestPage = lazy(() => import("./pages/Test"));
const Upload = lazy(() => import("./pages/Upload"));

export default function App() {
  return (
    <Routes>
      <Route
        path="race"
        element={
          <Suspense fallback={<div className="min-h-screen bg-cream" />}>
            <Race />
          </Suspense>
        }
      />
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
