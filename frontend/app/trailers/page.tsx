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
  const [trailer, setTrailer] = useState<TrailerRun | null>(runId ? null : demoTrailer);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!runId) return;
    let active = true;
    getTrailer(runId)
      .then((run) => { if (active) setTrailer(run); })
      .catch(() => { if (active) setError("This uploaded trailer run could not be loaded."); });
    return () => { active = false; };
  }, [runId]);

  if (error) return <main className="page"><div className="eyebrow">Trailer candidates / unavailable</div><h1>Run unavailable.</h1><p className="lede">{error}</p></main>;
  if (!trailer) return <main className="page"><div className="eyebrow">Trailer candidates / loading</div><h1>Shaping your trailer.</h1></main>;
  return <main className="page"><div className="trailer-header"><div><div className="eyebrow">Trailer candidates / screen 03 + 04</div><h1>{trailer.title}</h1><p style={{ margin: 0 }}>Candidate A · {trailer.audience} audience promise · {trailer.runtime}</p></div><div className="status-stack"><ValidationBadge status={trailer.validation.status} /><p className="mono" style={{ margin: "10px 0 0" }}>VALIDATED 09 SEP 2026</p></div></div><div className="trailer-grid"><section className="panel"><div className="section-head"><div><div className="eyebrow">Edit decision list</div><h2>One clean arc.</h2></div><p>{trailer.runtime} total</p></div><div className="timeline"><SegmentList segments={trailer.segments} mediaUrl={runId ? getMediaUrl(runId) : undefined} /></div><button className="primary-button" style={{ marginTop: 25 }}>Export EDL <ChevronDown size={15} style={{ verticalAlign: "middle" }} /></button></section><aside><section className="panel"><div className="eyebrow">Independent checks</div><h2 style={{ marginTop: 12 }}>Proof of fit.</h2>{trailer.validation.checks.map((check) => { const Icon = check.status === "pass" ? Check : check.status === "warning" ? TriangleAlert : X; return <div className="check-row" key={check.name}><Icon size={15} className={`check-${check.status}`} /><div><strong>{check.name}</strong><span>{check.detail}</span></div></div>; })}</section><section className="panel" style={{ marginTop: 22 }}><div className="eyebrow">Decision evidence</div><h2 style={{ marginTop: 12 }}>Why this cut?</h2><ul className="evidence">{trailer.evidence.map((item) => <li key={item}>{item}</li>)}</ul></section></aside></div></main>;
}
