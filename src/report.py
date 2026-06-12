"""Builds report.md with the aggregates: counts by category, priority and
department, plus the list of requests that need clarification."""

from collections import Counter

from .models import ClassifiedRequest


def _counts_table(title: str, counter: Counter, total: int) -> str:
    lines = [f"### {title}", "", "| Value | Count | Share |", "|---|---|---|"]
    for key, n in counter.most_common():
        share = round(n / total * 100) if total else 0
        lines.append(f"| {key} | {n} | {share}% |")
    return "\n".join(lines)


def build_report(results: list[ClassifiedRequest]) -> str:
    total = len(results)

    by_category = Counter(r.category.value for r in results)
    by_priority = Counter(r.priority.value for r in results)
    by_department = Counter((r.target_department or "unknown") for r in results)

    needs_clarification = [r for r in results if r.needs_clarification]
    parse_errors = [r for r in results if r.parse_error]

    out = []
    out.append("# Inbox requests report")
    out.append("")
    out.append(f"**Total requests:** {total}")
    out.append(f"**Need clarification:** {len(needs_clarification)}")
    out.append(f"**Failed to parse (fallback):** {len(parse_errors)}")
    out.append("")

    # keep priority in a fixed order so the table doesn't jump around
    prio_ordered = Counter()
    for p in ("high", "medium", "low"):
        if by_priority[p]:
            prio_ordered[p] = by_priority[p]

    out.append(_counts_table("By category", by_category, total))
    out.append("")
    out.append(_counts_table("By priority", prio_ordered, total))
    out.append("")
    out.append(_counts_table("By department", by_department, total))
    out.append("")

    out.append("### Need clarification")
    out.append("")
    if not needs_clarification:
        out.append("None.")
    else:
        for r in needs_clarification:
            out.append(f"**{r.id}** ({r.channel}) - {r.short_summary}")
            for q in r.clarification_questions:
                out.append(f"  - {q}")
            out.append("")

    return "\n".join(out).rstrip() + "\n"
