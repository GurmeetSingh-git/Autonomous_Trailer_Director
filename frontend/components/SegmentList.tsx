import { Film, Play, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { TrailerRun } from "@/lib/api";

export function SegmentList({ segments, mediaUrl }: { segments: TrailerRun["segments"]; mediaUrl?: string }) {
  const [selected, setSelected] = useState<TrailerRun["segments"][number] | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    if (!selected || !videoRef.current) return;
    const video = videoRef.current;
    const seekToSegment = () => { video.currentTime = timecodeToSeconds(selected.start); };
    video.addEventListener("loadedmetadata", seekToSegment, { once: true });
    return () => video.removeEventListener("loadedmetadata", seekToSegment);
  }, [selected]);

  const stopAtSegmentEnd = () => {
    if (videoRef.current && selected && videoRef.current.currentTime >= timecodeToSeconds(selected.end)) {
      videoRef.current.pause();
    }
  };

  return <>
    <div className="segment-list">{segments.map((segment, index) => <article className="segment-row" key={segment.id}>
    <div className="segment-index">0{index + 1}</div><div className="segment-icon"><Film size={17} /></div>
    <div className="segment-copy"><strong>{segment.label}</strong><span>{segment.tone} · {segment.start} — {segment.end}</span></div>
    <button className="icon-button" aria-label={`Preview ${segment.label}`} title={`Preview ${segment.label}`} onClick={() => setSelected(segment)}><Play size={15} fill="currentColor" /></button>
  </article>)}</div>
    {selected && <div className="preview-backdrop" role="presentation" onClick={() => setSelected(null)}><section className="preview-dialog" role="dialog" aria-modal="true" aria-label={`Preview ${selected.label}`} onClick={(event) => event.stopPropagation()}><button className="icon-button preview-close" aria-label="Close preview" title="Close preview" onClick={() => setSelected(null)}><X size={16} /></button>{mediaUrl ? <video ref={videoRef} className="preview-video" src={mediaUrl} controls autoPlay onTimeUpdate={stopAtSegmentEnd} /> : <p className="lede">Preview is available for uploaded runs, not the demo story.</p>}<strong>{selected.label}</strong><span className="mono">{selected.start} — {selected.end}</span></section></div>}
  </>;
}

function timecodeToSeconds(value: string): number {
  const parts = value.split(":").map(Number);
  if (parts.length !== 3 || parts.some(Number.isNaN)) return 0;
  return parts[0] * 3600 + parts[1] * 60 + parts[2];
}
