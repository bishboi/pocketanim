"use client";

import type { PreviewMark, Template } from "@/lib/templates";

function Mark({ mark }: { mark: PreviewMark }) {
  if (mark.t === "rect") {
    return (
      <rect
        x={mark.x}
        y={mark.y}
        width={mark.w}
        height={mark.h}
        rx={mark.rx ?? 0}
        fill={mark.fill ?? "none"}
        opacity={mark.opacity ?? 1}
      />
    );
  }
  if (mark.t === "circle") {
    return (
      <circle
        cx={mark.cx}
        cy={mark.cy}
        r={mark.r}
        fill={mark.fill ?? "none"}
        stroke={mark.stroke}
        strokeWidth={mark.sw ?? 0}
      />
    );
  }
  if (mark.t === "line") {
    return (
      <line
        x1={mark.x1}
        y1={mark.y1}
        x2={mark.x2}
        y2={mark.y2}
        stroke={mark.stroke}
        strokeWidth={mark.sw ?? 2}
        strokeLinecap="round"
      />
    );
  }
  return (
    <text
      x={mark.x}
      y={mark.y}
      fill={mark.fill}
      fontSize={mark.size}
      fontWeight={mark.weight ?? 500}
      textAnchor={mark.anchor ?? "start"}
      fontFamily="ui-sans-serif, system-ui, sans-serif"
    >
      {mark.text}
    </text>
  );
}

export function TemplateCard({
  template,
  selected,
  onSelect,
}: {
  template: Template;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      className={`w-[200px] shrink-0 overflow-hidden rounded-lg border-2 text-left transition-colors ${
        selected ? "bg-neutral-900" : "border-neutral-800 bg-neutral-950 hover:border-neutral-600"
      }`}
      style={selected ? { borderColor: template.palette[0] } : undefined}
    >
      <svg viewBox="0 0 320 180" className="block h-[112px] w-full" role="img" aria-label={`${template.name} preview`}>
        <rect width="320" height="180" fill={template.background} />
        {template.preview.map((mark, i) => (
          <Mark key={i} mark={mark} />
        ))}
      </svg>
      <div className="px-2.5 py-2">
        <p className="text-xs font-medium text-neutral-100">
          {template.name}
          {selected ? " · selected" : ""}
        </p>
        <p className="mt-0.5 line-clamp-2 text-[11px] leading-snug text-neutral-500">{template.summary}</p>
      </div>
    </button>
  );
}
