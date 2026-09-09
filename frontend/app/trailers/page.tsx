"use client";

import { Check, ChevronDown, TriangleAlert, X } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { ValidationBadge } from "@/components/ValidationBadge";
import { SegmentList } from "@/components/SegmentList";
import { demoTrailer, getMediaUrl, getTrailer, type TrailerRun } from "@/lib/api";

export default function TrailersPage() {
  const searchParams = useSearchParams();
  const runId = searchParams.get("run");
  const [trailer, setTrailer] = useState<TrailerRun | null>(searchParams.get("demo") ? demoTrailer : null);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  useEffect(() => {
    if (!runId || searchParams.get("demo")) return;
    getTrailer(runId).then(setTrailer).catch((reason) => setError(reason instanceof Error ? reason.message : "Unable to load trailer."));
  }, [runId, searchParams]);
  if (error) return <main className="page"><h1>Trailer unavailable</h1><p>{error}</p></main>;
  if (!trailer) return <main className="page"><p>Preparing trailer plan...</p></main>;
  const exportEdl = () => {
    const blob = new Blob([JSON.stringify(trailer, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${trailer.id}-edl.json`;
    link.click();
    URL.revokeObjectURL(url);
  };
  const previewSegment = (segment: TrailerRun["segments"][number]) => {
    if (runId) {
      const toSeconds = (timecode: string) => timecode.split(":").reduce((total, part) => total * 60 + Number(part), 0);
      window.open(`${getMediaUrl(runId)}#t=${toSeconds(segment.start)},${toSeconds(segment.end)}`, "_blank", "noopener,noreferrer");
      return;
    }
    setPreview(`${segment.label}: ${segment.start} - ${segment.end}`);
  };
  return <main className="page"><div className="trailer-header"><div><div className="eyebrow">Trailer candidates / screen 03 + 04</div><h1>{trailer.title}</h1><p style={{ margin: 0 }}>Candidate A · {trailer.audience} audience promise · {trailer.runtime}</p></div><div className="status-stack"><ValidationBadge status={trailer.validation.status} /><p className="mono" style={{ margin: "10px 0 0" }}>VALIDATED 09 SEP 2026</p></div></div><div className="trailer-grid"><section className="panel"><div className="section-head"><div><div className="eyebrow">Edit decision list</div><h2>One clean arc.</h2></div><p>{trailer.runtime} total</p></div><div className="timeline"><SegmentList segments={trailer.segments} onPreview={previewSegment} /></div><button className="primary-button" style={{ marginTop: 25 }} onClick={exportEdl}>Export EDL <ChevronDown size={15} style={{ verticalAlign: "middle" }} /></button>{preview && <p className="mono" style={{ marginBottom: 0 }}>Preview selected: {preview}</p>}</section><aside><section className="panel"><div className="eyebrow">Independent checks</div><h2 style={{ marginTop: 12 }}>Proof of fit.</h2>{trailer.validation.checks.map((check) => { const Icon = check.status === "pass" ? Check : check.status === "warning" ? TriangleAlert : X; return <div className="check-row" key={check.name}><Icon size={15} className={`check-${check.status}`} /><div><strong>{check.name}</strong><span>{check.detail}</span></div></div>; })}</section><section className="panel" style={{ marginTop: 22 }}><div className="eyebrow">Decision evidence</div><h2 style={{ marginTop: 12 }}>Why this cut?</h2><ul className="evidence">{trailer.evidence.map((item) => <li key={item}>{item}</li>)}</ul></section></aside></div></main>;
}
