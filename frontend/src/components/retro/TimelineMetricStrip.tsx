"use client";

import { Gauge } from "@/components/retro/DataViz";
import type { TimelinePreview } from "@/types/api";

const FACET_CAP = 3;

/**
 * Inline scalar preview for a Timeline row: measured value (mono) + a neutral
 * factual flag chip + the reference-range gauge (reused from the detail sheet)
 * + a few facet chips. Renders nothing when there's nothing to surface, so the
 * row falls back to its title-only form. `emphasis` is neutral-only — `notable`
 * marks an out-of-range/abnormal source value with a subtle accent, never a
 * good/bad clinical color.
 */
export function TimelineMetricStrip({ preview }: { preview?: TimelinePreview | null }) {
  if (!preview) return null;
  const { value, unit, flag, emphasis, gauge, facets } = preview;
  if (!value && !flag && !gauge && !(facets && facets.length)) return null;

  const shown = facets?.slice(0, FACET_CAP) ?? [];
  const overflow = (facets?.length ?? 0) - shown.length;

  return (
    <div className="tl-ms">
      <div className="tl-ms-row">
        {value && (
          <span className="tl-ms-val">
            {value}
            {unit && <span className="tl-ms-unit"> {unit}</span>}
          </span>
        )}
        {flag && (
          <span className="tag tl-ms-flag" data-emphasis={emphasis ?? "normal"}>
            {flag}
          </span>
        )}
        {shown.map((f) => (
          <span key={f} className="tl-ms-facet">
            {f}
          </span>
        ))}
        {overflow > 0 && <span className="tl-ms-facet">+{overflow}</span>}
      </div>
      {gauge && (
        <div className="tl-ms-gauge">
          <Gauge value={gauge.value} low={gauge.low} high={gauge.high} />
        </div>
      )}
    </div>
  );
}
