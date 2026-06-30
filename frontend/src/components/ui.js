import React from "react";

export function Card({ children, className = "", ...props }) {
  return (
    <div
      className={`border border-zinc-800 bg-zinc-900 rounded-xl ${className}`}
      {...props}
    >
      {children}
    </div>
  );
}

export function CardHeader({ title, subtitle, right, className = "" }) {
  return (
    <div className={`flex items-start justify-between border-b border-zinc-800 px-5 py-3.5 ${className}`}>
      <div>
        <h3 className="text-sm font-semibold tracking-tight text-zinc-50">{title}</h3>
        {subtitle && <p className="text-xs text-zinc-500 mt-0.5">{subtitle}</p>}
      </div>
      {right}
    </div>
  );
}

const variants = {
  primary: "bg-klein text-white hover:bg-blue-500 border-klein",
  danger: "bg-loss text-zinc-950 hover:bg-rose-300 border-loss",
  outline: "bg-transparent text-zinc-200 hover:bg-zinc-800 border-zinc-700",
  ghost: "bg-transparent text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100 border-transparent",
  success: "bg-profit text-zinc-950 hover:bg-emerald-300 border-profit",
};

export function Button({ variant = "primary", className = "", children, ...props }) {
  return (
    <button
      className={`inline-flex items-center justify-center gap-2 border px-3.5 py-2 text-sm font-medium rounded-lg transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${variants[variant]} ${className}`}
      {...props}
    >
      {children}
    </button>
  );
}

export function Input({ className = "", ...props }) {
  return (
    <input
      className={`w-full border border-zinc-800 bg-zinc-950 text-zinc-50 placeholder-zinc-600 px-3 py-2 text-sm rounded-lg outline-none focus:ring-1 focus:ring-klein focus:border-klein transition tabular ${className}`}
      {...props}
    />
  );
}

export function Badge({ children, tone = "default", className = "" }) {
  const tones = {
    default: "bg-zinc-800 text-zinc-300 border-zinc-700",
    klein: "bg-klein/15 text-blue-300 border-klein/30",
    danger: "bg-loss/15 text-loss border-loss/30",
    warn: "bg-warn/15 text-warn border-warn/30",
    success: "bg-profit/15 text-profit border-profit/30",
    muted: "bg-transparent text-zinc-500 border-zinc-700",
  };
  return (
    <span className={`inline-flex items-center gap-1 border px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide rounded-md ${tones[tone]} ${className}`}>
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
        checked ? (danger ? "bg-loss" : "bg-profit") : "bg-zinc-700"
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
    default: "text-zinc-50",
    profit: "text-profit",
    loss: "text-loss",
  }[tone];
  return (
    <div className="px-5 py-4">
      <div className="text-[11px] font-semibold uppercase tracking-wider text-zinc-500">{label}</div>
      <div className={`mt-1.5 font-mono text-2xl font-semibold tabular ${toneClass}`} data-testid={testid}>
        {value}
      </div>
      {sub && <div className="mt-0.5 text-xs text-zinc-500 font-mono tabular">{sub}</div>}
    </div>
  );
}

export function Spinner() {
  return (
    <div className="flex items-center justify-center py-10">
      <div className="h-6 w-6 animate-spin rounded-full border-2 border-zinc-700 border-t-klein" />
    </div>
  );
}

export function EmptyState({ title, hint, icon: Icon }) {
  return (
    <div className="flex flex-col items-center justify-center py-14 text-center">
      {Icon && (
        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-zinc-800 mb-4">
          <Icon size={22} className="text-zinc-500" />
        </div>
      )}
      <p className="text-sm font-medium text-zinc-300">{title}</p>
      {hint && <p className="text-xs text-zinc-500 mt-1 max-w-xs">{hint}</p>}
    </div>
  );
}

export function SectionTitle({ title, hint }) {
  return (
    <div className="flex items-baseline gap-2 mb-3">
      <h4 className="text-[11px] font-bold uppercase tracking-wider text-zinc-400">{title}</h4>
      {hint && <span className="text-xs text-zinc-600">{hint}</span>}
    </div>
  );
}
