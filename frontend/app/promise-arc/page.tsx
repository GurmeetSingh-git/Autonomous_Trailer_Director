"use client";

import Link from "next/link";
import { ArrowRight, Check, CircleAlert, Save } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { AudienceTabs } from "@/components/AudienceTabs";
import { getPromiseArc, type Audience, type PromiseArc, updatePromiseArc } from "@/lib/api";
const audiencePromises: Record<Audience, string> = {
  family: "Communicate warmth, stakes, and broad entertainment value.",
  young_adult: "Highlight pace, humour, identity, and character conflict.",
  dialect_region: "Show cultural and linguistic familiarity without stereotyping.",
};

export default function PromiseArcPage() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const runId = searchParams.get("run");
  const [arc, setArc] = useState<PromiseArc | null>(null);
  const [selectedAudience, setSelectedAudience] = useState<Audience>("family");
  const [audienceArcs, setAudienceArcs] = useState<Partial<Record<Audience, PromiseArc>>>({});
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (!runId) return;
    getPromiseArc(runId).then((loadedArc) => { setArc(loadedArc); setSelectedAudience(loadedArc.audience as Audience); setAudienceArcs({ [loadedArc.audience as Audience]: loadedArc }); }).catch((requestError) => setError(requestError instanceof Error ? requestError.message : "This run's audience promise could not be loaded."));
  }, [runId]);

  async function changeAudience(audience: Audience) {
    if (audience === selectedAudience) {
      if (!audienceArcs[audience]) await regenerateAudience();
      return;
    }
    if (!runId || !arc) return;
    setSelectedAudience(audience);
    setError("");
    const cachedArc = audienceArcs[audience];
    if (cachedArc) setArc(cachedArc);
    else setArc({ ...arc, audience, audience_profile: audience, audience_promise: `${audiencePromises[audience]} Ground the promise in the episode's verified characters and events.` });
    setSaved(false);
  }

  async function regenerateAudience() {
    if (!runId || selectedAudience === arc?.audience && audienceArcs[selectedAudience]) return;
    setSaving(true); setError("");
    try {
      const regeneratedArc = await getPromiseArc(runId, selectedAudience);
      setArc(regeneratedArc);
      setAudienceArcs((current) => ({ ...current, [selectedAudience]: regeneratedArc }));
      setSaved(true);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "The audience plan could not be regenerated.");
    } finally { setSaving(false); }
  }

  function updateBeat(index: number, field: keyof PromiseArc["narrative_arc"][number], value: string | boolean) {
    if (!arc) return;
    const narrative_arc = arc.narrative_arc.map((beat, beatIndex) => beatIndex === index ? { ...beat, [field]: value } : beat);
    setArc({ ...arc, narrative_arc });
    setSaved(false);
  }

  async function regenerateTimeline() {
    if (!runId || !arc) return;
    if (!audienceArcs[selectedAudience]) {
      await regenerateAudience();
      return;
    }
    setSaving(true); setError("");
    try {
      await updatePromiseArc(runId, arc);
      setSaved(true);
      router.push(`/trailers?run=${runId}`);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "The edited arc could not be validated.");
    } finally { setSaving(false); }
  }

  if (!runId) return <main className="page"><div className="eyebrow">Promise & arc / demo unavailable</div><h1>Choose an uploaded run.</h1><p className="lede">The editable promise phase needs a real analyzed episode and its source timecodes.</p><Link className="mono" href="/">Return to upload</Link></main>;
  if (error && !arc) return <main className="page"><div className="eyebrow">Promise & arc / unavailable</div><h1>Run unavailable.</h1><p className="lede">{error}</p><Link className="mono" href={`/story-map?run=${runId}`}>Back to story map</Link></main>;
  if (!arc) return <main className="page"><div className="eyebrow">Promise & arc / loading</div><h1>Committing to the audience.</h1></main>;

    return <main className="page"><div className="section-head"><div><div className="eyebrow">Promise & arc / screen 03</div><h1 style={{ fontSize: 54, marginBottom: 0 }}>Audience before footage.</h1></div><span className="validation-badge badge-pass"><Check size={13} /> {arc.validation_status}</span></div><p className="lede">Review the intent before the timeline is finalized. Edit beats and choose which promises to include, then regenerate once.</p><section className="panel promise-panel"><label className="upload-label">Audience lens</label><AudienceTabs value={arc.audience as Audience} onChange={changeAudience} /><label className="upload-label" htmlFor="audience-profile">Audience profile</label><input id="audience-profile" className="arc-input" value={arc.audience_profile} onChange={(event) => setArc({ ...arc, audience_profile: event.target.value })} /><label className="upload-label" htmlFor="audience-promise">Audience promise</label><textarea id="audience-promise" className="arc-textarea promise-copy" value={arc.audience_promise} onChange={(event) => { setArc({ ...arc, audience_promise: event.target.value }); setSaved(false); }} /><button className="audience-regenerate" type="button" onClick={regenerateAudience} disabled={saving}>{saving ? "Generating timestamps..." : "Regenerate audience timestamps"}</button></section><section className="arc-list"><div className="section-head"><div><div className="eyebrow">Narrative arc</div><h2>Map the emotional journey.</h2></div><span className="mono">{arc.narrative_arc.filter((beat) => beat.included).length} of {arc.narrative_arc.length} included</span></div>{arc.narrative_arc.map((beat, index) => <article className={`panel arc-card${beat.included ? "" : " arc-card-excluded"}`} key={`${beat.scene_id}-${index}`}><div className="arc-card-head"><label className="arc-include"><input type="checkbox" checked={beat.included} onChange={(event) => updateBeat(index, "included", event.target.checked)} /> Include</label><span className="segment-index">0{index + 1}</span><input className="arc-input beat-name" value={beat.beat_name} onChange={(event) => updateBeat(index, "beat_name", event.target.value)} /><span className="mono">{beat.scene_id}</span></div><div className="arc-times"><label>Source in<input className="arc-input" value={beat.source_in} onChange={(event) => updateBeat(index, "source_in", event.target.value)} /></label><label>Source out<input className="arc-input" value={beat.source_out} onChange={(event) => updateBeat(index, "source_out", event.target.value)} /></label></div><label className="upload-label">Emotional goal<textarea className="arc-textarea" value={beat.emotional_goal} onChange={(event) => updateBeat(index, "emotional_goal", event.target.value)} /></label></article>)}</section>{error && <p className="arc-error"><CircleAlert size={14} /> {error}</p>}<div className="arc-actions"><Link className="mono" href={`/story-map?run=${runId}`}>Back to story map</Link><button className="primary-button arc-submit" onClick={regenerateTimeline} disabled={saving}><Save size={15} /> {saving ? "Validating arc..." : "Regenerate validated timeline"} <ArrowRight size={15} /></button></div>{saved && <p className="arc-success">Arc saved and validated.</p>}</main>;
}
