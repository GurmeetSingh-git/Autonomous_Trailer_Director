import { Film, Play } from "lucide-react";
import type { TrailerRun } from "@/lib/api";

export function SegmentList({ segments }: { segments: TrailerRun["segments"] }) {
  return <div className="segment-list">{segments.map((segment, index) => <article className="segment-row" key={segment.id}>
    <div className="segment-index">0{index + 1}</div><div className="segment-icon"><Film size={17} /></div>
    <div className="segment-copy"><strong>{segment.label}</strong><span>{segment.tone} · {segment.start} — {segment.end}</span></div>
    <button className="icon-button" aria-label={`Preview ${segment.label}`} title={`Preview ${segment.label}`}><Play size={15} fill="currentColor" /></button>
  </article>)}</div>;
}
