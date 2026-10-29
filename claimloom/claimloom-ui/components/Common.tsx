import React from "react";

export function Card({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <section className={`rounded-xl border border-slate-200 bg-white shadow-sm ${className}`}>
      {children}
    </section>
  );
}

export function Empty({
  title,
  body,
  children,
}: {
  title: string;
  body: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-slate-300 bg-white px-6 py-12 text-center">
      <h3 className="text-sm font-semibold text-slate-800">{title}</h3>
      <p className="mt-1 max-w-sm text-sm text-slate-500">{body}</p>
      {children && <div className="mt-4 flex flex-wrap justify-center gap-2">{children}</div>}
    </div>
  );
}