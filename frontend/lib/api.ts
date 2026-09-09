export type Audience = "family" | "genre" | "prestige" | "action";
export type GeminiModel = "gemini-3.5-flash-lite" | "gemini-3.6-flash";

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
  title: string;
  audience: Audience;
  runtime: string;
  segments: { id: string; label: string; sceneId: string; start: string; end: string; tone: string }[];
  validation: Validation;
  evidence: string[];
};

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) throw new Error(`API request failed: ${response.status}`);
  return response.json() as Promise<T>;
}

export async function uploadEpisode(file: File, audience: Audience, model: GeminiModel): Promise<{ runId: string }> {
  const body = new FormData();
  body.append("episode", file);
  body.append("audience", audience);
  body.append("model", model);
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
