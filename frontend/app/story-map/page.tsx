"use client";

import Link from "next/link";
import { ArrowRight, CircleAlert, Map, Users } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { useEffect, useState } from "react";
import { demoStoryMap, getStoryMap, type StoryMap } from "@/lib/api";

function StoryMapPage() {
  const searchParams = useSearchParams();
  const runId = searchParams.get("run");
  const [map, setMap] = useState<StoryMap | null>(runId ? null : demoStoryMap);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!runId) return;
    let active = true;
    getStoryMap(runId)
      .then((storyMap) => { if (active) setMap(storyMap); })
      .catch(() => { if (active) setError("This uploaded run could not be loaded."); });
    return () => { active = false; };
  }, [runId]);

  if (error) return <main className="page"><div className="eyebrow">Story map / unavailable</div><h1 style={{ fontSize: 54 }}>Run unavailable.</h1><p className="lede">{error}</p><Link className="mono" href="/">Return to upload</Link></main>;
  if (!map) return <main className="page"><div className="eyebrow">Story map / loading</div><h1 style={{ fontSize: 54 }}>Reading your episode.</h1></main>;
  return <main className="page"><div className="section-head"><div><div className="eyebrow">Story map / screen 02</div><h1 style={{ fontSize: 54, marginBottom: 0 }}>{map.title}</h1></div><p>{searchParams.get("run") ? `RUN ${searchParams.get("run")}` : "DEMO RUN"}</p></div><p className="lede" style={{ marginBottom: 42 }}>{map.logline}</p><div className="map-grid"><section className="panel"><div className="eyebrow"><Users size={13} style={{ verticalAlign: "middle" }} /> Cast map</div><h2 style={{ marginTop: 12 }}>Who carries the story?</h2>{map.characters.map((character) => <div className="character" key={character.name}><span className={`avatar ${character.color}`} /><div><strong>{character.name}</strong><span>{character.role}</span></div></div>)}<div style={{ borderTop: "1px solid var(--line)", marginTop: 18, paddingTop: 20 }}><div className="eyebrow"><CircleAlert size={13} style={{ verticalAlign: "middle" }} /> Spoiler budget</div><div style={{ alignItems: "center", display: "flex", gap: 14, marginTop: 15 }}><strong style={{ fontSize: 30 }}>{map.spoilerBudget}%</strong><span style={{ color: "var(--muted)", fontSize: 12 }}>maximum reveal allowed<br />before the promise breaks</span></div><div style={{ background: "#e7ece5", height: 5, marginTop: 15 }}><div style={{ background: "var(--coral)", height: 5, width: `${map.spoilerBudget}%` }} /></div></div></section><section className="panel"><div className="eyebrow"><Map size={13} style={{ verticalAlign: "middle" }} /> Scene register</div><h2 style={{ marginTop: 12 }}>The shape of the episode.</h2>{map.scenes.map((scene) => <article className="scene-row" key={scene.id}><span className="timecode">{scene.timecode}</span><div><h3>{scene.title}</h3><p>{scene.description}</p><span className="mono">{scene.characters.join(" · ")}</span></div><span className={`spoiler ${scene.spoilerLevel}`}>{scene.spoilerLevel} risk</span></article>)}</section></div><div style={{ display: "flex", justifyContent: "flex-end", gap: 12, marginTop: 28 }}><Link className="primary-button" style={{ maxWidth: 240, textAlign: "center" }} href={runId ? `/promise-arc?run=${runId}` : "/promise-arc"}>Review promise & arc <ArrowRight size={15} style={{ verticalAlign: "middle" }} /></Link></div></main>;
}

export default function StoryMapRoute() {
  return <Suspense fallback={<main className="page"><h1>Reading your episode.</h1></main>}><StoryMapPage /></Suspense>;
}
