"use client";

import Link from "next/link";
import { ArrowRight, Check, CircleAlert } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { getPromiseArc, reprocessPlot, type Audience, type PromiseArc, updatePromiseArc } from "@/lib/api";

export default function PlotPage() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const runId = searchParams.get("run");
  const audience = (searchParams.get("audience") ?? "family") as Audience;
  const [arc, setArc] = useState<PromiseArc | null>(null);
  const [error, setError] = useState("");
  const [accepting, setAccepting] = useState(false);
  const [feedback, setFeedback] = useState("");
  const [reprocessing, setReprocessing] = useState(false);

  useEffect(() => {
    if (!runId) return;
    getPromiseArc(runId, audience).then((loadedArc) => { setArc(loadedArc); setFeedback(loadedArc.feedback ?? ""); }).catch((requestError) => setError(requestError instanceof Error ? requestError.message : "The trailer plot could not be generated."));
  }, [runId, audience]);

  function updateBeat(index: number, field: "beat_name" | "emotional_goal", value: string) {
    if (!arc) return;
    setArc({ ...arc, narrative_arc: arc.narrative_arc.map((beat, beatIndex) => beatIndex === index ? { ...beat, [field]: value } : beat) });
  }

  async function acceptPlot() {
    if (!runId || !arc) return;
    setAccepting(true); setError("");
    try {
      await updatePromiseArc(runId, { ...arc, feedback });
      router.push(`/trailers?run=${runId}`);
    } catch (requestError) { setError(requestError instanceof Error ? requestError.message : "The plot could not be accepted."); setAccepting(false); }
  }

  async function reprocess() {
    if (!runId) return;
    setReprocessing(true); setError("");
    try {
      const freshPlot = await reprocessPlot(runId, audience, feedback);
      setArc(freshPlot);
      setFeedback(freshPlot.feedback ?? feedback);
    } catch (requestError) { setError(requestError instanceof Error ? requestError.message : "The plot could not be reprocessed."); }
    finally { setReprocessing(false); }
  }

  if (!runId) return <main className="page"><div className="eyebrow">Trailer plot</div><h1>Choose an uploaded run.</h1><Link className="mono" href="/">Return to upload</Link></main>;
  if (error && !arc) return <main className="page"><div className="eyebrow">Trailer plot / unavailable</div><h1>Plot unavailable.</h1><p className="lede">{error}</p><Link className="mono" href={`/audience?run=${runId}`}>Back to audience selection</Link></main>;
  if (!arc) return <main className="page"><div className="eyebrow">Trailer plot / generating</div><h1>Finding the promise.</h1><p className="lede">The director is shaping the emotional journey before choosing source clips.</p></main>;

  return <main className="page"><div className="section-head"><div><div className="eyebrow">Trailer plot / screen 04</div><h1 style={{ fontSize: 54, marginBottom: 0 }}>The promise on screen.</h1></div><span className="validation-badge badge-pass"><Check size={13} /> PLOT READY</span></div><p className="lede">Edit the suggested story and emotional beats. Source timecodes and timeline settings stay hidden until you approve this plot.</p><section className="panel plot-hero"><div className="eyebrow">{arc.audience} audience promise</div><textarea className="arc-textarea promise-copy" value={arc.audience_promise} onChange={(event) => setArc({ ...arc, audience_promise: event.target.value })} /><p>{arc.audience_profile}</p></section><section className="plot-beats"><div className="section-head"><div><div className="eyebrow">Suggested trailer plot</div><h2>Edit the beats before footage.</h2></div><span className="mono">{arc.narrative_arc.filter((beat) => beat.included).length} beats</span></div>{arc.narrative_arc.filter((beat) => beat.included).map((beat, index) => <article className="panel plot-beat" key={`${beat.scene_id}-${index}`}><span className="plot-beat-number">0{index + 1}</span><div className="plot-beat-fields"><input className="arc-input" value={beat.beat_name} onChange={(event) => updateBeat(index, "beat_name", event.target.value)} aria-label={`Beat ${index + 1} title`} /><textarea className="arc-textarea" value={beat.emotional_goal} onChange={(event) => updateBeat(index, "emotional_goal", event.target.value)} aria-label={`Beat ${index + 1} goal`} /><span className="mono">Source-backed story beat · clip selection follows approval</span></div></article>)}</section><section className="panel plot-feedback"><div className="eyebrow">Director notes</div><h2>What should change?</h2><textarea className="arc-textarea" value={feedback} onChange={(event) => setFeedback(event.target.value)} placeholder="Make the opening hook faster, increase warmth, remove a spoiler, or emphasize the child's perspective..." /></section>{error && <p className="arc-error">{error}</p>}<div className="plot-actions"><Link className="audience-regenerate" href={`/audience?run=${runId}`}>Change audience</Link><button className="plot-reprocess" onClick={reprocess} disabled={reprocessing || accepting}>{reprocessing ? "Reprocessing..." : "Reprocess plot"}</button><button className="primary-button plot-accept" onClick={acceptPlot} disabled={accepting || reprocessing}><Check size={15} /> {accepting ? "Building timeline..." : "Accept plot & choose clips"}<ArrowRight size={15} /></button></div><div className="plot-note"><CircleAlert size={15} /> Reprocess asks the director for a fresh plot. Accept only when the story beats are right.</div></main>;
}
