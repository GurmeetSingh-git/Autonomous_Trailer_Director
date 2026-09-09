"use client";

import { Check, ChevronDown, TriangleAlert, X } from "lucide-react";
import { ValidationBadge } from "@/components/ValidationBadge";
import { SegmentList } from "@/components/SegmentList";
import { demoTrailer } from "@/lib/api";

export default function TrailersPage() {
  const trailer = demoTrailer;
  return <main className="page"><div className="trailer-header"><div><div className="eyebrow">Trailer candidates / screen 03 + 04</div><h1>{trailer.title}</h1><p style={{ margin: 0 }}>Candidate A · {trailer.audience} audience promise · {trailer.runtime}</p></div><div className="status-stack"><ValidationBadge status={trailer.validation.status} /><p className="mono" style={{ margin: "10px 0 0" }}>VALIDATED 09 SEP 2026</p></div></div><div className="trailer-grid"><section className="panel"><div className="section-head"><div><div className="eyebrow">Edit decision list</div><h2>One clean arc.</h2></div><p>01:32 total</p></div><div className="timeline"><SegmentList segments={trailer.segments} /></div><button className="primary-button" style={{ marginTop: 25 }}>Export EDL <ChevronDown size={15} style={{ verticalAlign: "middle" }} /></button></section><aside><section className="panel"><div className="eyebrow">Independent checks</div><h2 style={{ marginTop: 12 }}>Proof of fit.</h2>{trailer.validation.checks.map((check) => { const Icon = check.status === "pass" ? Check : check.status === "warning" ? TriangleAlert : X; return <div className="check-row" key={check.name}><Icon size={15} className={`check-${check.status}`} /><div><strong>{check.name}</strong><span>{check.detail}</span></div></div>; })}</section><section className="panel" style={{ marginTop: 22 }}><div className="eyebrow">Decision evidence</div><h2 style={{ marginTop: 12 }}>Why this cut?</h2><ul className="evidence">{trailer.evidence.map((item) => <li key={item}>{item}</li>)}</ul></section></aside></div></main>;
}
