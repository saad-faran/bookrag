"use client";
import React, { useState } from "react";
import { BookOpen, Loader2, Sparkles } from "lucide-react";
import { login, register } from "../lib/auth.js";

export default function Auth({ onAuthed }) {
  const [mode, setMode] = useState("login");   // "login" | "register"
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setErr(""); setBusy(true);
    try {
      const user = mode === "login"
        ? await login(email.trim(), password)
        : await register(email.trim(), password, name.trim());
      onAuthed(user);
    } catch (ex) {
      setErr(ex.message || "Something went wrong");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="h-full w-full flex items-center justify-center p-4">
      <div className="w-full max-w-sm">
        <div className="flex items-center gap-2 justify-center mb-6">
          <BookOpen className="text-indigo-400" size={26} />
          <div className="text-2xl font-extrabold tracking-tight">
            Book<span className="gradient-text">RAG</span>
          </div>
        </div>

        <div className="glass p-6">
          <div className="text-lg font-bold mb-1">
            {mode === "login" ? "Welcome back" : "Create your account"}
          </div>
          <div className="text-[12px] text-slate-400 mb-5">
            {mode === "login"
              ? "Sign in to your grounded finance assistant."
              : "Start asking grounded questions over the corpus."}
          </div>

          <form onSubmit={submit} className="space-y-3">
            {mode === "register" && (
              <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Name (optional)"
                className="w-full glass !rounded-xl px-3 py-2.5 text-[14px] bg-transparent outline-none
                           focus:border-indigo-500/60" />
            )}
            <input value={email} onChange={(e) => setEmail(e.target.value)} type="email" required
              placeholder="Email" autoComplete="email"
              className="w-full glass !rounded-xl px-3 py-2.5 text-[14px] bg-transparent outline-none focus:border-indigo-500/60" />
            <input value={password} onChange={(e) => setPassword(e.target.value)} type="password" required
              placeholder="Password" autoComplete={mode === "login" ? "current-password" : "new-password"}
              className="w-full glass !rounded-xl px-3 py-2.5 text-[14px] bg-transparent outline-none focus:border-indigo-500/60" />

            {err && <div className="text-[12px] text-rose-400">{err}</div>}

            <button type="submit" disabled={busy}
              className="gradient-btn w-full text-white font-semibold rounded-xl py-2.5 flex items-center justify-center gap-2 disabled:opacity-60">
              {busy ? <Loader2 size={16} className="animate-spin" /> : <Sparkles size={15} />}
              {mode === "login" ? "Sign in" : "Create account"}
            </button>
          </form>

          <div className="text-[12px] text-slate-400 mt-4 text-center">
            {mode === "login" ? "New here? " : "Already have an account? "}
            <button onClick={() => { setErr(""); setMode(mode === "login" ? "register" : "login"); }}
              className="text-indigo-300 hover:text-indigo-200 font-medium">
              {mode === "login" ? "Create an account" : "Sign in"}
            </button>
          </div>
        </div>
        <div className="text-[11px] text-slate-500 text-center mt-4">
          Agentic, grounded RAG over a multimodal finance corpus.
        </div>
      </div>
    </div>
  );
}
