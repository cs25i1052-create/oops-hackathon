import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ClaimLoom | Intelligent Brand Governance Platform",
  description:
    "Pre-publication brand compliance, multimodal PDF redlining, and hybrid pgvector/BM25 RAG verification.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="bg-slate-50 text-slate-900 min-h-screen antialiased">
        {children}
      </body>
    </html>
  );
}