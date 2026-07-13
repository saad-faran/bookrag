import "./globals.css";

export const metadata = {
  title: "BookRAG — Finance Intelligence",
  description: "Agentic, grounded RAG over a multimodal finance corpus.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en" className="dark">
      <body>{children}</body>
    </html>
  );
}
