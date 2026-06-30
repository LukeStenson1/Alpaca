import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;

const client = axios.create({ baseURL: API, timeout: 30000 });

export default client;

// ---------- formatting helpers ----------
export const fmtUSD = (v, dp = 2) => {
  if (v === null || v === undefined || isNaN(v)) return "—";
  return `$${Number(v).toLocaleString("en-US", {
    minimumFractionDigits: dp,
    maximumFractionDigits: dp,
  })}`;
};

export const fmtPct = (v, dp = 2) => {
  if (v === null || v === undefined || isNaN(v)) return "—";
  const sign = v > 0 ? "+" : "";
  return `${sign}${Number(v).toFixed(dp)}%`;
};

export const fmtNum = (v, dp = 4) => {
  if (v === null || v === undefined || isNaN(v)) return "—";
  return Number(v).toLocaleString("en-US", { maximumFractionDigits: dp });
};

export const fmtDate = (iso) => {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString("en-US", {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
};
