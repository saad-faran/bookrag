"use client";
import React from "react";
import { Minus, Maximize2, Minimize2 } from "lucide-react";

// Minimize (collapse to a strip) + maximize/restore controls for a panel header.
export default function PanelControls({ onMin, maxed, onToggleMax }) {
  return (
    <div className="flex items-center gap-0.5 shrink-0">
      {onMin && !maxed && (
        <button className="icon-btn" title="Minimize panel" onClick={onMin}>
          <Minus size={15} />
        </button>
      )}
      <button className="icon-btn" title={maxed ? "Restore panel" : "Maximize panel"} onClick={onToggleMax}>
        {maxed ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
      </button>
    </div>
  );
}
