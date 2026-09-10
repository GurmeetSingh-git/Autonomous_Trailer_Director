export type Audience = "family" | "young_adult" | "dialect_region";

export type Scene = {
  id: string;
  title: string;
  timecode: string;
  description: string;
  characters: string[];
  spoilerLevel: "low" | "medium" | "high";
  selected?: boolean;
};

export type StoryMap = {
  title: string;
  logline: string;
  characters: { name: string; role: string; color: string }[];
  scenes: Scene[];
  spoilerBudget: number;
};

export type Validation = {
  status: "PASS" | "PASS_WITH_WARNINGS" | "REJECT";
  checks: { name: string; status: "pass" | "warning" | "fail"; detail: string }[];
};

export type TrailerRun = {
  id: string;
  trailer_id?: string;
  title: string;
  audience: Audience;
  runtime: string;
  duration_seconds?: number;
  audience_promise?: string;
  segments: {
    id: string;
    label: string;
    scene_id?: string;
    sceneId: string;
    source_in?: string;
    source_out?: string;
    start: string;
    end: string;
    tone: string;
    audio?: string;
    subtitle?: string;
    reason?: string;
    evidence?: string[];
    risk_flags?: string[];
    validation?: { status: string; checks: Validation["checks"] };
    is_included?: boolean;
  }[];
  validation: Validation;
  evidence: string[];
  review_status?: "PENDING" | "PASSED" | "NEEDS_REVISION";
  review_feedback?: string;
  review_round?: number;
};

export type PromiseBeat = {
  scene_id: string;
  beat_name: string;
  source_in: string;
  source_out: string;
  emotional_goal: string;
  included: boolean;
};

export type PromiseArc = {
  audience: string;
  audience_profile: string;
  audience_promise: string;
  narrative_arc: PromiseBeat[];
  validation_status: Validation["status"];
  feedback?: string;
};

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    let detail = "";
    try {
      const body = await response.json() as { detail?: string };
      detail = body.detail ? `: ${body.detail}` : "";
    } catch {
      // Keep the status error when the response is not JSON.
    }
    throw new Error(`API request failed: ${response.status}${detail}`);
  }
  const text = await response.text();
  if (!text.trim()) throw new Error(`API returned an empty response for ${path}. Restart the API and try again.`);
  try {
    return JSON.parse(text) as T;
  } catch {
    throw new Error(`API returned invalid JSON for ${path}. Check the API logs.`);
  }
}

export type EvidencePackage = {
  sceneDescriptions?: File | null;
  dialogueSubtitles?: File | null;
  policiesMetadata?: File | null;
};

export async function uploadEpisode(file: File, audience: Audience, evidence: EvidencePackage = {}): Promise<{ runId: string }> {
  const body = new FormData();
  body.append("episode", file);
  body.append("audience", audience);
  if (evidence.sceneDescriptions) body.append("scene_descriptions", evidence.sceneDescriptions);
  if (evidence.dialogueSubtitles) body.append("dialogue_subtitles", evidence.dialogueSubtitles);
  if (evidence.policiesMetadata) body.append("policies_metadata", evidence.policiesMetadata);
  const response = await fetch(`${API_URL}/runs`, { method: "POST", body });
  if (!response.ok) throw new Error(`Upload failed: ${response.status}`);
  return response.json() as Promise<{ runId: string }>;
}

export function getStoryMap(runId: string): Promise<StoryMap> {
  return request<StoryMap>(`/runs/${runId}/story-map`);
}

export function getTrailer(runId: string): Promise<TrailerRun> {
  return request<TrailerRun>(`/runs/${runId}/trailer`);
}

export function getMediaUrl(runId: string): string {
  return `${API_URL}/runs/${runId}/media`;
}

export function getRenderedTrailerUrl(runId: string): string {
  return `${API_URL}/runs/${runId}/render?t=${Date.now()}`;
}

export function renderTrailer(runId: string): Promise<{ url: string; filename: string }> {
  return request<{ url: string; filename: string }>(`/runs/${runId}/render`, { method: "POST" });
}

export function reviewTrailer(runId: string, action: "pass" | "fail" | "regenerate", feedback = ""): Promise<{ trailer: TrailerRun; review_status: string; review_round: number }> {
  return request<{ trailer: TrailerRun; review_status: string; review_round: number }>(`/runs/${runId}/review`, {
    method: "POST",
    body: JSON.stringify({ action, feedback }),
  });
}

export function getPromiseArc(runId: string, audience?: Audience): Promise<PromiseArc> {
  const query = audience ? `?audience=${encodeURIComponent(audience)}` : "";
  return request<PromiseArc>(`/runs/${runId}/promise-arc${query}`);
}

export function updatePromiseArc(runId: string, arc: PromiseArc): Promise<{ promise_arc: PromiseArc; trailer: TrailerRun }> {
  return request<{ promise_arc: PromiseArc; trailer: TrailerRun }>(`/runs/${runId}/promise-arc`, {
    method: "POST",
    body: JSON.stringify(arc),
  });
}

export function reprocessPlot(runId: string, audience: Audience, feedback = ""): Promise<PromiseArc> {
  return request<PromiseArc>(`/runs/${runId}/plot/reprocess?audience=${encodeURIComponent(audience)}`, {
    method: "POST",
    body: JSON.stringify({ feedback }),
  });
}

export function startTrailerRun(runId: string): Promise<TrailerRun> {
  return request<TrailerRun>(`/runs/${runId}/plan`, { method: "POST" });
}

export const demoStoryMap: StoryMap = {
  title: "The Last Light",
  logline: "When an apprentice cartographer discovers a vanished city on an impossible map, she must choose between the life she knows and the world hiding in plain sight.",
  spoilerBudget: 22,
  characters: [
    { name: "Mara Venn", role: "The cartographer", color: "coral" },
    { name: "Ilan", role: "Her brother", color: "sky" },
    { name: "The Keeper", role: "A hidden guide", color: "gold" },
  ],
  scenes: [
    { id: "s01", title: "The impossible coastline", timecode: "00:04:12", description: "Mara finds a coastline that does not exist in any atlas.", characters: ["Mara Venn"], spoilerLevel: "low", selected: true },
    { id: "s07", title: "A door in the archive", timecode: "00:18:44", description: "A midnight key reveals a door behind the city archive.", characters: ["Mara Venn", "Ilan"], spoilerLevel: "low", selected: true },
    { id: "s13", title: "The first crossing", timecode: "00:39:08", description: "The siblings step into a city lit by a second moon.", characters: ["Mara Venn", "Ilan", "The Keeper"], spoilerLevel: "medium", selected: true },
    { id: "s18", title: "The choice", timecode: "00:54:27", description: "Mara learns what the map was made to protect.", characters: ["Mara Venn", "The Keeper"], spoilerLevel: "high" },
  ],
};

export const demoTrailer: TrailerRun = {
  id: "demo-run",
  title: "The Last Light",
  audience: "family",
  runtime: "01:32",
  segments: [
    { id: "a", label: "The question", sceneId: "s01", start: "00:04:12", end: "00:04:35", tone: "wonder" },
    { id: "b", label: "The threshold", sceneId: "s07", start: "00:18:44", end: "00:19:20", tone: "discovery" },
    { id: "c", label: "The promise", sceneId: "s13", start: "00:39:08", end: "00:39:51", tone: "adventure" },
  ],
  validation: {
    status: "PASS_WITH_WARNINGS",
    checks: [
      { name: "Existence", status: "pass", detail: "3 of 3 source clips found" },
      { name: "Spoiler budget", status: "pass", detail: "18 / 22 points used" },
      { name: "Rights", status: "pass", detail: "All assets cleared" },
      { name: "Accessibility", status: "warning", detail: "Audio description still pending" },
      { name: "Rating", status: "pass", detail: "Suitable for family audience" },
    ],
  },
  evidence: ["Opening establishes the mystery in under 5 seconds.", "The threshold scene pays off the audience promise without revealing the final act.", "Dialogue density stays below the family-audience threshold."],
};
