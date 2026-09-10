"use client";

import { Check, ChevronDown, Download, RefreshCw, TriangleAlert, X } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { ValidationBadge } from "@/components/ValidationBadge";
import { SegmentList } from "@/components/SegmentList";
import { demoTrailer, getMediaUrl, getRenderedTrailerUrl, getTrailer, renderTrailer, reviewTrailer, type TrailerRun } from "@/lib/api";

function TrailersPage() {
  const searchParams = useSearchParams();
  const runId = searchParams.get("run");
  const [trailer, setTrailer] = useState<TrailerRun | null>(runId ? null : demoTrailer);
  const [error, setError] = useState("");
  const [rendering, setRendering] = useState(Boolean(runId));
  const [rendered, setRendered] = useState(false);
  const [feedback, setFeedback] = useState("");
  const [reviewMessage, setReviewMessage] = useState("");
  const [reviewing, setReviewing] = useState(false);

  useEffect(() => {
    if (!runId) return;
    let active = true;
    getTrailer(runId)
      .then(async (run) => {
        if (!active) return;
        setTrailer(run);
        await renderTrailer(runId);
        if (active) { setRendered(true); setRendering(false); }
      })
      .catch((requestError) => { if (active) setError(requestError instanceof Error ? requestError.message : "This uploaded trailer run could not be loaded."); });
    return () => { active = false; };
  }, [runId]);

  if (error) return <main className="page"><div className="eyebrow">Trailer candidates / unavailable</div><h1>Run unavailable.</h1><p className="lede">{error}</p></main>;
  if (!trailer) return <main className="page"><div className="eyebrow">Trailer candidates / loading</div><h1>Shaping your trailer.</h1></main>;
  async function submitReview(action: "pass" | "fail" | "regenerate") {
    if (!runId) { setReviewMessage("Upload a real episode to use review controls."); return; }
    if (action === "fail" && !feedback.trim()) { setReviewMessage("Add feedback before requesting changes."); return; }
    setReviewing(true); setReviewMessage("");
    try {
      const result = await reviewTrailer(runId, action, feedback);
      setTrailer(result.trailer);
      if (action === "regenerate") { setRendered(false); await renderTrailer(runId); setRendered(true); setFeedback(""); }
      setReviewMessage(action === "pass" ? "Review approved." : action === "fail" ? "Revision requested." : "Trailer regenerated from your feedback.");
    } catch (requestError) { setReviewMessage(requestError instanceof Error ? requestError.message : "Review update failed."); }
    finally { setReviewing(false); }
  }
  const exportEdl = () => { const edl = { trailer_id: trailer.trailer_id ?? `${trailer.audience}_v1`, audience: trailer.audience, duration_seconds: trailer.duration_seconds ?? 0, audience_promise: trailer.audience_promise ?? "", segments: trailer.segments, validation: trailer.validation }; const blob = new Blob([JSON.stringify(edl, null, 2)], { type: "application/json" }); const url = URL.createObjectURL(blob); const link = document.createElement("a"); link.href = url; link.download = `${trailer.id}-edl.json`; link.click(); URL.revokeObjectURL(url); };
  return <main className="page"><div className="trailer-header"><div><div className="eyebrow">Final render / screen 04</div><h1>{trailer.title}</h1><p style={{ margin: 0 }}>Validated trailer · {trailer.audience} audience promise · {trailer.runtime}</p></div><div className="status-stack"><ValidationBadge status={trailer.validation.status} /><p className="mono" style={{ margin: "10px 0 0" }}>{rendering ? "RENDERING FINAL CUT" : "FINAL CUT READY"}</p></div></div><div className="trailer-grid"><section className="panel"><div className="section-head"><div><div className="eyebrow">Final video preview</div><h2>{rendering ? "Compiling the selected beats." : "Preview the validated cut."}</h2></div><p>{trailer.runtime} total</p></div>{runId && <video className="preview-video" controls preload="metadata" src={rendered ? getRenderedTrailerUrl(runId) : undefined} />}{!runId && <p className="lede">Upload a real episode to render and preview the final video.</p>}<div className="timeline"><SegmentList segments={trailer.segments} mediaUrl={runId ? getMediaUrl(runId) : undefined} /></div><div style={{ display: "flex", gap: 10, marginTop: 25 }}><button className="primary-button" onClick={exportEdl}><Download size={15} style={{ verticalAlign: "middle" }} /> Export EDL</button>{runId && <a className="primary-button" href={rendered ? getRenderedTrailerUrl(runId) : undefined} download={`${trailer.id}-trailer.mp4`} style={{ textAlign: "center", opacity: rendered ? 1 : .5, pointerEvents: rendered ? "auto" : "none" }}>Download video</a>}</div></section><aside><section className="panel"><div className="eyebrow">Validation certificate</div><h2 style={{ marginTop: 12 }}>Proof of fit.</h2>{trailer.validation.checks.map((check, index) => { const Icon = check.status === "pass" ? Check : check.status === "warning" ? TriangleAlert : X; return <div className="check-row" key={`${check.name}-${index}`}><Icon size={15} className={`check-${check.status}`} /><div><strong>{check.name}</strong><span>{check.detail}</span></div></div>; })}</section><section className="panel" style={{ marginTop: 22 }}><div className="eyebrow">Decision evidence</div><h2 style={{ marginTop: 12 }}>Why this cut?</h2><ul className="evidence">{trailer.evidence.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ul></section></aside></div></main>;
}

export default function TrailersRoute() {
  return <Suspense fallback={<main className="page"><h1>Shaping your trailer.</h1></main>}><TrailersPage /></Suspense>;
}
