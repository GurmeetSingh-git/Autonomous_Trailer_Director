"use client";

import type { Audience } from "@/lib/api";

const audiences: { value: Audience; label: string; note: string }[] = [
  { value: "family", label: "Family", note: "Wonder first" },
  { value: "young_adult", label: "Young adult", note: "Pace and identity" },
  { value: "dialect_region", label: "Dialect / region", note: "Cultural familiarity" },
];

export function AudienceTabs({ value, onChange }: { value: Audience; onChange: (value: Audience) => void }) {
  return <div className="audience-tabs" role="tablist" aria-label="Trailer audience">
    {audiences.map((audience) => <button key={audience.value} className={value === audience.value ? "audience-tab active" : "audience-tab"} onClick={() => onChange(audience.value)} role="tab" aria-selected={value === audience.value}>
      <strong>{audience.label}</strong><span>{audience.note}</span>
    </button>)}
  </div>;
}
