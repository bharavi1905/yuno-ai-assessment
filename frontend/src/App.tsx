import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { ToastProvider } from "./components/Toast";
import Layout from "./components/Layout";
import Dashboard from "./pages/Dashboard";
import Agents from "./pages/Agents";
import Workflows from "./pages/Workflows";
import Runs from "./pages/Runs";
import Monitor from "./pages/Monitor";
import ErrorBoundary from "./components/ErrorBoundary";

export default function App() {
  return (
    <ToastProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Layout />}>
            <Route index element={<Navigate to="/dashboard" replace />} />
            <Route path="dashboard" element={<ErrorBoundary><Dashboard /></ErrorBoundary>} />
            <Route path="agents" element={<ErrorBoundary><Agents /></ErrorBoundary>} />
            <Route path="workflows" element={<ErrorBoundary><Workflows /></ErrorBoundary>} />
            <Route path="runs" element={<ErrorBoundary><Runs /></ErrorBoundary>} />
            <Route path="runs/:runId" element={<ErrorBoundary><Runs /></ErrorBoundary>} />
            <Route path="monitor" element={<ErrorBoundary><Monitor /></ErrorBoundary>} />
          </Route>
        </Routes>
      </BrowserRouter>
    </ToastProvider>
  );
}
