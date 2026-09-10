"use client";

import { Check, RefreshCw, TriangleAlert, X } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { ValidationBadge } from "@/components/ValidationBadge";
import { getRenderedTrailerUrl, getTrailer, reviewTrailer, type TrailerRun } from "@/lib/api";

function ReviewPage() {
  const searchParams = useSearchParams();
  const runId = searchParams.get("run");
  const [trailer, setTrailer] = useState<TrailerRun | null>(null);
  const [feedback, setFeedback] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(Boolean(runId));

  useEffect(() => {
    if (!runId) return;
    getTrailer(runId).then(setTrailer).catch((error) => setMessage(error instanceof Error ? error.message : "Review could not be loaded.")).finally(() => setLoading(false));
  }, [runId]);

  async function submit(action: "pass" | "fail" | "regenerate") {
    if (!runId) { setMessage("Open review from an uploaded trailer run."); return; }
    if (action === "fail" && !feedback.trim()) { setMessage("Add feedback before requesting changes."); return; }
    setLoading(true); setMessage("");
    try {
      const result = await reviewTrailer(runId, action, feedback);
      setTrailer(result.trailer);
      setMessage(action === "pass" ? "Trailer approved for export." : action === "fail" ? "Revision requested." : "A revised trailer is ready for review.");
      if (action === "regenerate") setFeedback("");
    } catch (error) { setMessage(error instanceof Error ? error.message : "Review update failed."); }
    finally { setLoading(false); }
  }

  if (!runId) return <main className="page"><div className="eyebrow">Director review</div><h1>Choose a trailer run.</h1><p className="lede">Open this page with a generated trailer run to review its video and suggested plot.</p></main>;
  if (!trailer && loading) return <main className="page"><div className="eyebrow">Director review</div><h1>Loading the cut.</h1></main>;
  if (!trailer) return <main className="page"><div className="eyebrow">Director review</div><h1>Review unavailable.</h1><p className="lede">{message}</p></main>;

  return <main className="page"><div className="review-header"><div><div className="eyebrow">Director review / human checkpoint</div><h1>{trailer.title}</h1><p className="lede">Review the suggested trailer plot, inspect the cut, and approve or send focused notes back to the director.</p></div><ValidationBadge status={trailer.validation.status} /></div><div className="review-grid"><section><video className="review-video" controls preload="metadata" src={getRenderedTrailerUrl(runId)} /><div className="review-plot panel"><div className="eyebrow">Suggested trailer plot</div><h2>{trailer.audience_promise ?? "Audience promise"}</h2><ol>{trailer.segments.map((segment) => <li key={segment.id}><strong>{segment.label}</strong><span>{segment.start} - {segment.end} · {segment.tone}</span><p>{segment.reason ?? "Source-backed story beat."}</p></li>)}</ol></div></section><aside><section className="panel"><div className="eyebrow">Validation</div>{trailer.validation.checks.map((check, index) => { const Icon = check.status === "pass" ? Check : check.status === "warning" ? TriangleAlert : X; return <div className="check-row" key={`${check.name}-${index}`}><Icon size={15} className={`check-${check.status}`} /><div><strong>{check.name}</strong><span>{check.detail}</span></div></div>; })}</section><section className="panel review-controls"><div className="eyebrow">Review decision</div><p className="review-status">Round {trailer.review_round ?? 0} · {trailer.review_status ?? "PENDING"}</p><textarea className="review-feedback" value={feedback} onChange={(event) => setFeedback(event.target.value)} placeholder="Make the opening hook faster, remove a spoiler, change the emotional emphasis..." /><div className="review-actions"><button className="review-pass" onClick={() => submit("pass")} disabled={loading}><Check size={15} /> Pass</button><button className="review-fail" onClick={() => submit("fail")} disabled={loading}><X size={15} /> Request changes</button><button className="review-regenerate" onClick={() => submit("regenerate")} disabled={loading}><RefreshCw size={15} /> Regenerate</button></div>{message && <p className="review-message">{message}</p>}</section></aside></div></main>;
}

export default function ReviewRoute() {
  return <Suspense fallback={<main className="page"><h1>Loading the cut.</h1></main>}><ReviewPage /></Suspense>;
}
