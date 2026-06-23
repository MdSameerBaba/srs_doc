"""
assembler.py — Stitches individual SRS sections into a final IEEE 830 document.
Also generates a verification summary report.
"""

import json
from datetime import datetime


# ─────────────────────────────────────────────────────────────
# Final SRS assembly
# ─────────────────────────────────────────────────────────────

def assemble_srs(
    sections: dict[int, str],
    canonical: dict,
    project_name: str = "Unknown Project",
) -> str:
    """
    Combine all generated sections into a single Markdown SRS document.
    Section 11 (Traceability Matrix) is auto-generated from canonical FRs
    if not already present in `sections`.
    """
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")

    header = f"""\
# Software Requirements Specification

**Project:** {project_name}
**Standard:** IEEE 830 / ISO/IEC 29148
**Generated:** {ts}
**Generator:** AI SRS Generator (Graphifyy + Ollama)

> ⚠️ This document was auto-generated from source code analysis.
> All `[TBD]` entries require manual completion before formal release.
> Verify every `[evidence: ...]` citation against the frozen `canonical.json`.

---

"""

    body_parts: list[str] = [header]

    for section_num in sorted(sections.keys()):
        md = sections[section_num].strip()
        body_parts.append(md)
        body_parts.append("\n\n---\n\n")

    # ── Auto-generate Section 11 if missing ────────────────
    if 11 not in sections:
        body_parts.append(_build_traceability_matrix(canonical))
        body_parts.append("\n\n---\n\n")

    return "".join(body_parts)


def _build_traceability_matrix(canonical: dict) -> str:
    frs = canonical.get("functional_requirements", [])
    rows = [
        "## 11. Traceability Matrix\n",
        "| FR ID | Title | Actor | Evidence | Confidence | "
        "Implementation Module | Test Case ID | Verification Status |",
        "|-------|-------|-------|----------|------------|"
        "----------------------|--------------|---------------------|",
    ]
    for fr in frs:
        fr_id   = fr.get("id", "")
        title   = (fr.get("title") or "")[:55].replace("|", "\\|")
        actor   = (fr.get("actor") or "").replace("|", "\\|")
        ev_ids  = ", ".join(str(e) for e in fr.get("evidence_ids", []))
        conf    = fr.get("confidence", "")
        rows.append(
            f"| {fr_id} | {title} | {actor} | {ev_ids} | {conf} "
            f"| [TBD] | [TBD] | UNVERIFIED |"
        )
    return "\n".join(rows)


# ─────────────────────────────────────────────────────────────
# Verification summary report
# ─────────────────────────────────────────────────────────────

def generate_verification_report(verification_results: dict[int, dict]) -> str:
    """Return a Markdown report summarising per-section audit results."""
    pass_count = sum(
        1 for r in verification_results.values()
        if isinstance(r, dict) and r.get("status") == "PASS"
    )
    total = len(verification_results)

    lines = [
        "# Verification Report",
        f"\n**{pass_count}/{total} sections passed verification**\n",
    ]

    for section_num in sorted(verification_results.keys()):
        report = verification_results[section_num]
        if not isinstance(report, dict):
            continue
        status = report.get("status", "UNKNOWN")
        icon   = "✅" if status == "PASS" else ("⚠️" if status == "NEEDS_REVIEW" else "❌")
        lines.append(f"### {icon} Section {section_num} — `{status}`")

        if report.get("missing"):
            lines.append(f"- **Missing FRs:** {', '.join(report['missing'])}")
        if report.get("hallucinated"):
            lines.append(f"- **Hallucinated FRs:** {', '.join(report['hallucinated'])}")
        if report.get("renamed"):
            for r in report["renamed"]:
                lines.append(
                    f"- **Renamed:** `{r.get('id')}` "
                    f"canonical=*{r.get('canonical_title')}* "
                    f"→ generated as *{r.get('generated_as')}*"
                )
        if report.get("uncited_claims"):
            lines.append(
                f"- **Uncited claims:** {len(report['uncited_claims'])} "
                f"(first: *{report['uncited_claims'][0][:80]}*)"
            )
        lines.append("")

    return "\n".join(lines)
