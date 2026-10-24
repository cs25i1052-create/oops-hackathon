import { Issue } from "./schema";

export interface TextSegment {
  text: string;
  issue?: Issue;
}

export function toSegments(text: string, issues: Issue[]): TextSegment[] {
  const claimedRanges: { s: number; e: number }[] = [];

  const spans = issues
    .filter((i) => i.violation_type !== "Visual" && i.flagged_text.trim().length > 0)
    .map((issue) => {
      let s = issue.start ?? -1;
      let e = issue.end ?? -1;

      const sliceMatches = s >= 0 && e > s && text.slice(s, e) === issue.flagged_text;
      if (!sliceMatches) {
        let searchFrom = 0;
        s = -1;
        while (searchFrom < text.length) {
          const found = text.indexOf(issue.flagged_text, searchFrom);
          if (found === -1) break;
          const foundEnd = found + issue.flagged_text.length;
          const overlaps = claimedRanges.some((r) => !(foundEnd <= r.s || found >= r.e));
          if (!overlaps) {
            s = found;
            e = foundEnd;
            break;
          }
          searchFrom = found + 1;
        }
      }

      if (s >= 0 && e > s) {
        claimedRanges.push({ s, e });
        return { s, e, issue };
      }
      return null;
    })
    .filter((x): x is { s: number; e: number; issue: Issue } => x !== null)
    .sort((a, b) => a.s - b.s);

  const out: TextSegment[] = [];
  let cur = 0;

  for (const sp of spans) {
    if (sp.s < cur) continue;
    if (sp.s > cur) {
      out.push({ text: text.slice(cur, sp.s) });
    }
    out.push({ text: text.slice(sp.s, sp.e), issue: sp.issue });
    cur = sp.e;
  }

  if (cur < text.length) {
    out.push({ text: text.slice(cur) });
  }

  return out;
}