"use client";
import dynamic from "next/dynamic";

// The whole dashboard is client-only (React Flow + localStorage touch window); disable SSR.
const AuthGate = dynamic(() => import("../components/AuthGate.jsx"), {
  ssr: false,
  loading: () => (
    <div className="h-full w-full flex items-center justify-center text-slate-400">
      Loading BookRAG…
    </div>
  ),
});

export default function Page() {
  return <AuthGate />;
}
