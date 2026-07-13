"use client";
import dynamic from "next/dynamic";

// The whole dashboard is client-only (React Flow touches window); disable SSR.
const App = dynamic(() => import("../components/App.jsx"), {
  ssr: false,
  loading: () => (
    <div className="h-full w-full flex items-center justify-center text-slate-400">
      Loading BookRAG…
    </div>
  ),
});

export default function Page() {
  return <App />;
}
