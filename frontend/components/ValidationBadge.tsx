import { Check, TriangleAlert, X } from "lucide-react";
import type { Validation } from "@/lib/api";

export function ValidationBadge({ status }: { status: Validation["status"] }) {
  const config = {
    PASS: { label: "Pass", icon: Check, className: "badge-pass" },
    PASS_WITH_WARNINGS: { label: "Pass with notes", icon: TriangleAlert, className: "badge-warning" },
    REJECT: { label: "Rejected", icon: X, className: "badge-fail" },
  }[status];
  const Icon = config.icon;
  return <span className={`validation-badge ${config.className}`}><Icon size={14} /> {config.label}</span>;
}
