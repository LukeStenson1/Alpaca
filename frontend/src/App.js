import React from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { ToastProvider } from "./components/Toast";
import { SystemProvider } from "./components/SystemContext";
import Layout from "./components/Layout";
import Overview from "./pages/Overview";
import Watchlist from "./pages/Watchlist";
import TradeHistory from "./pages/TradeHistory";
import Suggestions from "./pages/Suggestions";
import Reports from "./pages/Reports";
import Strategy from "./pages/Strategy";
import Settings from "./pages/Settings";

export default function App() {
  return (
    <ToastProvider>
      <SystemProvider>
        <BrowserRouter>
          <Layout>
            <Routes>
              <Route path="/" element={<Overview />} />
              <Route path="/watchlist" element={<Watchlist />} />
              <Route path="/trades" element={<TradeHistory />} />
              <Route path="/suggestions" element={<Suggestions />} />
              <Route path="/reports" element={<Reports />} />
              <Route path="/strategy" element={<Strategy />} />
              <Route path="/settings" element={<Settings />} />
            </Routes>
          </Layout>
        </BrowserRouter>
      </SystemProvider>
    </ToastProvider>
  );
}
