import React from "react";

export function Card({ children, className = "", ...props }) {
  return (
    <div
      className={`border border-zinc-200 bg-white rounded-md ${className}`}
      {...props}
    >
      {children}
    </div>
  );
}

export function CardHeader({ title, subtitle, right, className = "" }) {
  return (
    <div className={`flex items-start justify-between border-b border-zinc-200 px-5 py-3.5 ${className}`}>
      <div>
        <h3 className="text-sm font-semibold tracking-tight text-zinc-950">{title}</h3>
        {subtitle && <p className="text-xs text-zinc-500 mt-0.5">{subtitle}</p>}
      </div>
      {right}
    </div>
  );
}

const variants = {
  primary: "bg-klein text-white hover:bg-[#002288] border-klein",
  danger: "bg-loss text-white hover:bg-red-700 border-loss",
  outline: "bg-white text-zinc-800 hover:bg-zinc-50 border-zinc-300",
  ghost: "bg-transparent text-zinc-600 hover:bg-zinc-100 border-transparent",
  success: "bg-profit text-white hover:bg-green-700 border-profit",
};

export function Button({ variant = "primary", className = "", children, ...props }) {
  return (
    <button
      className={`inline-flex items-center justify-center gap-2 border px-3.5 py-2 text-sm font-medium rounded-md transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${variants[variant]} ${className}`}
      {...props}
    >
      {children}
    </button>
  );
}

export function Input({ className = "", ...props }) {
  return (
    <input
      className={`w-full border border-zinc-300 bg-white px-3 py-2 text-sm rounded-md outline-none focus:ring-1 focus:ring-zinc-950 focus:border-zinc-950 transition tabular ${className}`}
      {...props}
    />
  );
}

export function Badge({ children, tone = "default", className = "" }) {
  const tones = {
    default: "bg-zinc-100 text-zinc-700 border-zinc-200",
    klein: "bg-klein text-white border-klein",
    danger: "bg-loss text-white border-loss",
    warn: "bg-warn text-white border-warn",
    success: "bg-profit text-white border-profit",
    muted: "bg-white text-zinc-500 border-zinc-300",
  };
  return (
    <span className={`inline-flex items-center gap-1 border px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide rounded ${tones[tone]} ${className}`}>
      {children}
    </span>
  );
}

export function Toggle({ checked, onChange, disabled, danger, testid }) {
  return (
    <button
      type="button"
      data-testid={testid}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors disabled:opacity-50 ${
        checked ? (danger ? "bg-loss" : "bg-profit") : "bg-zinc-300"
      }`}
    >
      <span
        className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
          checked ? "translate-x-6" : "translate-x-1"
        }`}
      />
    </button>
  );
}

export function Stat({ label, value, sub, tone = "default", testid }) {
  const toneClass = {
    default: "text-zinc-950",
    profit: "text-profit",
    loss: "text-loss",
  }[tone];
  return (
    <div className="px-5 py-4">
      <div className="text-[11px] font-semibold uppercase tracking-wide text-zinc-500">{label}</div>
      <div className={`mt-1 font-mono text-2xl font-semibold tabular ${toneClass}`} data-testid={testid}>
        {value}
      </div>
      {sub && <div className="mt-0.5 text-xs text-zinc-500 font-mono tabular">{sub}</div>}
    </div>
  );
}

export function Spinner() {
  return (
    <div className="flex items-center justify-center py-10">
      <div className="h-6 w-6 animate-spin rounded-full border-2 border-zinc-300 border-t-klein" />
    </div>
  );
}

export function EmptyState({ title, hint }) {
  return (
    <div className="flex flex-col items-center justify-center py-14 text-center">
      <img
        src="https://images.unsplash.com/photo-1622547748225-3fc4abd2cca0?crop=entropy&cs=srgb&fm=jpg&q=85&w=200"
        alt=""
        className="h-16 w-16 object-cover rounded opacity-60 mb-4"
      />
      <p className="text-sm font-medium text-zinc-700">{title}</p>
      {hint && <p className="text-xs text-zinc-400 mt-1 max-w-xs">{hint}</p>}
    </div>
  );
}
