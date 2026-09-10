"use client";

import Link from "next/link";
import { ArrowRight, Users } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { AudienceTabs } from "@/components/AudienceTabs";
import type { Audience } from "@/lib/api";
import { useState } from "react";

export default function AudiencePage() {
  const searchParams = useSearchParams();
  const runId = searchParams.get("run");
  const [audience, setAudience] = useState<Audience>("family");

  if (!runId) return <main className="page"><div className="eyebrow">Audience lens</div><h1>Choose an uploaded run.</h1><p className="lede">Audience selection needs a real analyzed episode.</p><Link className="mono" href="/">Return to upload</Link></main>;
  return <main className="page"><div className="eyebrow">Audience lens / screen 03</div><h1>Who are we inviting in?</h1><p className="lede">Choose the audience first. The director will shape a trailer plot around that promise before selecting a single clip.</p><section className="panel audience-choice"><div className="eyebrow"><Users size={13} style={{ verticalAlign: "middle" }} /> Direction</div><h2>Set the audience lens.</h2><AudienceTabs value={audience} onChange={setAudience} /><Link className="primary-button audience-next" href={`/plot?run=${runId}&audience=${audience}`}>Generate trailer plot <ArrowRight size={15} /></Link></section></main>;
}
