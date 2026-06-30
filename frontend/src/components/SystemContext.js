import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import client from "../api";

const SystemCtx = createContext(null);
export const useSystem = () => useContext(SystemCtx);

export function SystemProvider({ children }) {
  const [state, setState] = useState(null);
  const [alerts, setAlerts] = useState([]);

  const refresh = useCallback(async () => {
    try {
      const [s, a] = await Promise.all([
        client.get("/system/state"),
        client.get("/alerts", { params: { limit: 50 } }),
      ]);
      setState(s.data);
      setAlerts(a.data);
    } catch (e) {
      // keep previous state on transient errors
    }
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 15000);
    return () => clearInterval(id);
  }, [refresh]);

  return (
    <SystemCtx.Provider value={{ state, alerts, refresh, setState }}>
      {children}
    </SystemCtx.Provider>
  );
}
