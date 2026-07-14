"use client";
import React, { useEffect, useState } from "react";
import App from "./App.jsx";
import Auth from "./Auth.jsx";
import { getToken, getUser, logout as doLogout } from "../lib/auth.js";

export default function AuthGate() {
  const [user, setUser] = useState(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (getToken()) setUser(getUser());
    setReady(true);
  }, []);

  if (!ready) return null;
  if (!user) return <Auth onAuthed={setUser} />;
  return <App user={user} onLogout={() => { doLogout(); setUser(null); }} />;
}
