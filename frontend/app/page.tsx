"use client";

import { useEffect, useState } from "react";
import { ArrowUpRight, FileVideo, Sparkles } from "lucide-react";
import Link from "next/link";
import { AudienceTabs } from "@/components/AudienceTabs";
import { demoStoryMap, retryStoryMap, type Audience, type EvidencePackage, type UploadProgress, uploadEpisode } from "@/lib/api";

const evidenceDropzones = [
  { key: "sceneDescriptions", title: "Scene descriptions", detail: "JSON, TXT, or CSV", accept: ".json,.txt,.csv,application/json,text/plain,text/csv" },
  { key: "dialogueSubtitles", title: "Dialogue and subtitles", detail: "SRT, VTT, or TXT", accept: ".srt,.vtt,.txt,text/plain" },
  { key: "policiesMetadata", title: "Policies, contracts & metadata", detail: "PDF, JSON, or TXT", accept: ".pdf,.json,.txt,application/pdf,application/json,text/plain" },
] as const;

export default function HomePage() {
  const [audience, setAudience] = useState<Audience>("family");
  const [file, setFile] = useState<File | null>(null);
  const [evidence, setEvidence] = useState<EvidencePackage>({});
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState<UploadProgress | null>(null);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [message, setMessage] = useState("");
  const [recoverableRunId, setRecoverableRunId] = useState<string | null>(null);

  useEffect(() => {
    if (!loading || !progress) return;
    const stageStartedAt = Date.now();
    const interval = window.setInterval(
      () => setElapsedSeconds(Math.floor((Date.now() - stageStartedAt) / 1000)),
      1000,
    );
    return () => window.clearInterval(interval);
  }, [loading, progress?.stage]);

  async function handleSubmit() {
    if (!file) { setMessage("Choose an episode package to begin."); return; }
    setLoading(true); setProgress({ stage: "uploading", message: "Uploading episode...", percentage: 0 }); setMessage(""); setRecoverableRunId(null);
    try {
      const result = await uploadEpisode(file, audience, evidence, setProgress);
      window.location.href = `/story-map?run=${result.runId}`;
    } catch (requestError) {
      const errorMessage = requestError instanceof Error ? requestError.message : "Upload analysis failed.";
      const runId = errorMessage.match(/\[recoverableRunId=([\da-f-]+)\]/i)?.[1] ?? null;
      setRecoverableRunId(runId);
      setMessage(runId ? `${errorMessage.replace(/\s*\[recoverableRunId=[\da-f-]+\]/i, "")} Saved analysis can be retried.` : errorMessage);
    } finally { setLoading(false); setProgress(null); }
  }

  async function handleRetry() {
    if (!recoverableRunId) return;
    setLoading(true); setProgress({ stage: "retrying", message: "Retrying saved analysis..." }); setMessage("");
    try {
      await retryStoryMap(recoverableRunId);
      window.location.href = `/story-map?run=${recoverableRunId}`;
    } catch (requestError) {
      setMessage(requestError instanceof Error ? requestError.message : "The saved analysis could not be recovered.");
    } finally { setLoading(false); setProgress(null); }
  }

  return (
    <main className="page">
      <div className="hero-grid">
        <section>
          <div className="eyebrow">Autonomous Trailer Director / 01</div>
          <h1>Turn an episode into a reason to watch.</h1>
          <p className="lede">A deliberate workspace for finding the story, choosing the promise, and proving every cut earns its place.</p>
          <div className="hero-stamp"><strong>Audience before footage.</strong><span>The director commits to a promise before a single candidate clip is selected.</span></div>
        </section>
        <section className="upload-panel">
          <div className="upload-inner">
            <div className="upload-label">New direction</div>
            <h2>Bring in an episode.</h2>
            <p style={{ color: "#d8ebe5", fontSize: 13 }}>Upload a package and set the audience lens. The system will map the story before it touches the timeline.</p>
            <label className="dropzone">
              <FileVideo size={26} color="#e2b34f" />
              <strong>{file?.name ?? "Drop an episode package"}</strong>
              <span>{file ? `${((file.size) / 1024 / 1024).toFixed(1)} MB selected` : "MP4, MOV, or a prepared episode folder"}</span>
              <input type="file" accept="video/mp4,video/quicktime,.zip" onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
            </label>
            <div className="evidence-heading"><div className="upload-label">Evidence packages</div><span>Optional, improves grounding</span></div>
            <div className="evidence-dropzones">
              {evidenceDropzones.map((zone) => {
                const selected = evidence[zone.key];
                return <label className="evidence-dropzone" key={zone.key}><strong>{zone.title}</strong><span>{selected ? selected.name : zone.detail}</span><input type="file" accept={zone.accept} onChange={(event) => setEvidence((current) => ({ ...current, [zone.key]: event.target.files?.[0] ?? null }))} /></label>;
              })}
            </div>
            <div className="upload-label">Audience lens</div>
            <AudienceTabs value={audience} onChange={setAudience} />
            <button className="primary-button" onClick={handleSubmit} disabled={loading}>{loading ? "Analysis in progress..." : "Build the story map ->"}</button>
            {loading && progress && <section className="analysis-progress" aria-live="polite">
              <div className="analysis-progress-heading"><span className="analysis-spinner" aria-hidden="true" /><strong>{progress.message}</strong></div>
              <div
                className="analysis-progress-track"
                role="progressbar"
                aria-label={progress.message}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={progress.percentage}
              >
                <span className={progress.percentage === undefined ? "analysis-progress-indeterminate" : ""} style={progress.percentage === undefined ? undefined : { width: `${progress.percentage}%` }} />
              </div>
              <div className="analysis-progress-footer">
                <span>{progress.percentage === undefined ? "Processing can take several minutes for a full episode." : `${progress.percentage}% uploaded`}</span>
                <span>{Math.floor(elapsedSeconds / 60)}:{String(elapsedSeconds % 60).padStart(2, "0")} elapsed</span>
              </div>
              {progress.stage === "detecting_scenes" && <p className="analysis-progress-note">PySceneDetect is installed and scanning video frames. The page will move to transcription when the scan finishes.</p>}
            </section>}
            {message && <p style={{ color: "#f7cfbf", fontSize: 12 }}>{message}</p>}
            {recoverableRunId && <button className="mono" onClick={handleRetry} disabled={loading}>{loading ? "Retrying saved analysis..." : "Retry saved analysis"}</button>}
          </div>
        </section>
      </div>
      <div style={{ display: "flex", gap: 22, marginTop: 58 }}><Link className="mono" href="/story-map?demo=true">Explore sample story map <ArrowUpRight size={13} style={{ verticalAlign: "middle" }} /></Link><span className="mono"><Sparkles size={13} style={{ verticalAlign: "middle" }} /> Replayable decisions</span></div>
      <span style={{ display: "none" }}>{demoStoryMap.title}</span>
    </main>
  );
}
