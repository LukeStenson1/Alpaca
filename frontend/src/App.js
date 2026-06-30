import React from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { ToastProvider } from "./components/Toast";
import { SystemProvider } from "./components/SystemContext";
import Layout from "./components/Layout";
import Overview from "./pages/Overview";
import Research from "./pages/Research";
import Settings from "./pages/Settings";
import History from "./pages/History";

export default function App() {
  return (
    <ToastProvider>
      <SystemProvider>
        <BrowserRouter>
          <Layout>
            <Routes>
              <Route path="/" element={<Overview />} />
              <Route path="/research" element={<Research />} />
              <Route path="/settings" element={<Settings />} />
              <Route path="/history" element={<History />} />
              {/* legacy redirects */}
              <Route path="/watchlist" element={<Research initialTab="watchlist" />} />
              <Route path="/influencers" element={<Research initialTab="influencers" />} />
              <Route path="/strategy" element={<Settings />} />
              <Route path="/suggestions" element={<Settings />} />
              <Route path="/trades" element={<History initialTab="trades" />} />
              <Route path="/reports" element={<History initialTab="reports" />} />
            </Routes>
          </Layout>
        </BrowserRouter>
      </SystemProvider>
    </ToastProvider>
  );
}
