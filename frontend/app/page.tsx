"use client";

import { useState } from "react";
import { ArrowUpRight, FileVideo, Sparkles } from "lucide-react";
import Link from "next/link";
import { AudienceTabs } from "@/components/AudienceTabs";
import { demoStoryMap, type Audience, uploadEpisode } from "@/lib/api";

export default function HomePage() {
  const [audience, setAudience] = useState<Audience>("family");
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");

  async function handleSubmit() {
    if (!file) { setMessage("Choose an episode package to begin."); return; }
    setLoading(true); setMessage("");
    try {
      const result = await uploadEpisode(file, audience);
      window.location.href = `/story-map?run=${result.runId}`;
    } catch {
      setMessage("API is offline. The sample story map is ready to explore.");
      window.location.href = "/story-map?demo=true";
    } finally { setLoading(false); }
  }

  return <main className="page"><div className="hero-grid"><section><div className="eyebrow">Autonomous Trailer Director / 01</div><h1>Turn an episode into a reason to watch.</h1><p className="lede">A deliberate workspace for finding the story, choosing the promise, and proving every cut earns its place.</p><div className="hero-stamp"><strong>Audience before footage.</strong><span>The director commits to a promise before a single candidate clip is selected.</span></div></section><section className="upload-panel"><div className="upload-inner"><div className="upload-label">New direction</div><h2>Bring in an episode.</h2><p style={{ color: "#d8ebe5", fontSize: 13 }}>Upload a package and set the audience lens. The system will map the story before it touches the timeline.</p><label className="dropzone"><FileVideo size={26} color="#e2b34f" /><strong>{file ? file.name : "Drop an episode package"}</strong><span>{file ? `${(file.size / 1024 / 1024).toFixed(1)} MB selected` : "MP4, MOV, or a prepared episode folder"}</span><input type="file" accept="video/*,.zip" onChange={(event) => setFile(event.target.files?.[0] ?? null)} /></label><div className="upload-label">Audience lens</div><AudienceTabs value={audience} onChange={setAudience} /><button className="primary-button" onClick={handleSubmit} disabled={loading}>{loading ? "Reading episode..." : "Build the story map  →"}</button>{message && <p style={{ color: "#f7cfbf", fontSize: 12 }}>{message}</p>}</div></section></div><div style={{ display: "flex", gap: 22, marginTop: 58 }}><Link className="mono" href="/story-map?demo=true">Explore sample story map <ArrowUpRight size={13} style={{ verticalAlign: "middle" }} /></Link><span className="mono"><Sparkles size={13} style={{ verticalAlign: "middle" }} /> Replayable decisions</span></div><span style={{ display: "none" }}>{demoStoryMap.title}</span></main>;
}
