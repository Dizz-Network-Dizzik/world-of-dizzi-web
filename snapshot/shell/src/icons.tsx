import type { JSX } from "react";

// Eigene Line-Icons (Stil: dünne Outline, currentColor) — kein Emoji,
// gleiche Schule wie die Trading-Bot-Icon-Sprite, aber matt statt Glow.
const P = (d: string): JSX.Element => (
  <svg className="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor"
    strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <path d={d} />
  </svg>
);

const ICONS: Record<string, JSX.Element> = {
  chart: P("M3 20h18M6 16l4-6 3 3 5-8"),
  box: P("M3 8l9-5 9 5v8l-9 5-9-5V8m9 5L3 8m9 5l9-5m-9 5v8"),
  globe: P("M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18m-9-9h18M12 3c2.5 2.4 3.8 5.6 3.8 9S14.5 18.6 12 21c-2.5-2.4-3.8-5.6-3.8-9S9.5 5.4 12 3"),
  folder: P("M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7"),
  coins: P("M12 9a7 3 0 1 0 0-6 7 3 0 0 0 0 6m-7-3v6c0 1.7 3.1 3 7 3s7-1.3 7-3V6m-14 6v6c0 1.7 3.1 3 7 3s7-1.3 7-3v-6"),
  stamp: P("M9 11V6a3 3 0 1 1 6 0v5m-9 0h12l1 4H5l1-4m-2 8h16"),
  share: P("M18 8a3 3 0 1 0-2.8-4M18 8a3 3 0 0 1-2.8-2M6 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6m12 6a3 3 0 1 0-2.8-4M8.7 10.7l6.6-3.4m-6.6 6l6.6 3.4"),
  wand: P("M5 19L17 7m-2-3l1 2 2 1-2 1-1 2-1-2-2-1 2-1 1-2m4 9l.7 1.3L21 16l-1.3.7L19 18l-.7-1.3L17 16l1.3-.7L19 14"),
  pulse: P("M3 12h4l2-7 4 14 2-7h6"),
  chip: P("M9 9h6v6H9V9m-4 3h2m10 0h2M12 5v2m0 10v2M7 5v2m10-2v2M7 17v2m10-2v2M5 7h14v10H5V7"),
  brain: P("M12 4a3 3 0 0 0-3 3c-2 0-3.5 1.5-3.5 3.5 0 1 .4 1.9 1 2.5-.6.6-1 1.5-1 2.5A3.5 3.5 0 0 0 9 19c.3 1.2 1.5 2 3 2s2.7-.8 3-2a3.5 3.5 0 0 0 3.5-3.5c0-1-.4-1.9-1-2.5.6-.6 1-1.5 1-2.5C18.5 8.5 17 7 15 7a3 3 0 0 0-3-3m0 0v17m-3-8h6"),
  lock: P("M7 11V8a5 5 0 0 1 10 0v3m-12 0h14v9H5v-9m7 3v3"),
  mic: P("M12 3a3 3 0 0 1 3 3v5a3 3 0 0 1-6 0V6a3 3 0 0 1 3-3m-7 8a7 7 0 0 0 14 0m-7 7v3m-4 0h8"),
  bell: P("M12 4a5 5 0 0 1 5 5v3l2 4H5l2-4V9a5 5 0 0 1 5-5m-2 16a2 2 0 0 0 4 0"),
  speaker: P("M4 9v6h4l5 4V5L8 9H4m12-1a5 5 0 0 1 0 8m2.5-10.5a8 8 0 0 1 0 13"),
  link: P("M10 14a4 4 0 0 0 6 .5l3-3a4 4 0 0 0-6-6l-1.5 1.5M14 10a4 4 0 0 0-6-.5l-3 3a4 4 0 0 0 6 6l1.5-1.5"),
  send: P("M4 12l16-7-4 7 4 7-16-7m16 0H9"),
  gear: P("M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6m7-3a7 7 0 0 0-.1-1.2l2-1.5-2-3.4-2.3 1a7 7 0 0 0-2-1.2L14.2 3h-4l-.4 2.5a7 7 0 0 0-2 1.2l-2.3-1-2 3.4 2 1.5a7 7 0 0 0 0 2.4l-2 1.5 2 3.4 2.3-1a7 7 0 0 0 2 1.2l.4 2.5h4l.4-2.5a7 7 0 0 0 2-1.2l2.3 1 2-3.4-2-1.5c.06-.4.1-.8.1-1.2"),
  shield: P("M12 3l7 3v5c0 4.4-3 8.4-7 10-4-1.6-7-5.6-7-10V6l7-3m-3 9l2 2 4-4"),
};

export function Icon({ name }: { name: string }): JSX.Element {
  return ICONS[name] ?? ICONS.box;
}
