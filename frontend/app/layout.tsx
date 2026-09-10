import type { Metadata } from "next";
import Link from "next/link";
import { Clapperboard } from "lucide-react";
import "./globals.css";

export const metadata: Metadata = { title: "Director's Room", description: "Autonomous trailer direction workspace" };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body><div className="shell"><nav className="nav"><Link className="brand" href="/"><span className="brand-mark"><Clapperboard size={16} /></span> Director's Room</Link><div className="nav-links"><Link href="/story-map">Story map</Link><Link href="/trailers">Trailers</Link><Link href="/review">Review</Link></div></nav>{children}</div></body></html>;
}
