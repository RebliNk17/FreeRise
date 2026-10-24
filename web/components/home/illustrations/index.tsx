// Animated insight illustrations (inline SVG). Element styles are the final frame; the
// a-* classes in globals.css play an intro + subtle loop only under .ill-play (the active card).
import { useId } from "react";
import type { IllustrationName } from "@/lib/insights";

const INK = "var(--ill-ink)";
const PAPER = "var(--ill-paper)";
const HOT = "var(--ill-hot)";
const SUN = "var(--sun)";
const SUN_EDGE = "#d9a12c";
const MINT = "#7fd1b5";
const MINT_DARK = "#4fb592";
const DEEP = "var(--brand-fill)";
const d = (ms: number) => ({ animationDelay: `${ms}ms` });

function Coin({ x, y, r = 9 }: { x: number; y: number; r?: number }) {
  return (
    <>
      <circle cx={x} cy={y} r={r} fill={SUN} stroke={SUN_EDGE} strokeWidth="2" />
      <text x={x} y={y + 0.5} textAnchor="middle" dominantBaseline="central" fontSize={r * 1.1} fontWeight="800" fill="#8a5d00">
        ₪
      </text>
    </>
  );
}

function Spike() {
  return (
    <>
      <path d="M40 100h124" stroke={INK} strokeOpacity=".3" strokeWidth="2" strokeLinecap="round" />
      {[
        [54, 34],
        [82, 46],
        [110, 40],
      ].map(([x, h], k) => (
        <rect key={x} className="o-b a-grow" style={d(k * 90)} x={x} y={100 - h} width="20" height={h} rx="4" fill={INK} fillOpacity=".28" />
      ))}
      <rect className="o-b a-spike" x="138" y="24" width="20" height="76" rx="4" fill={HOT} />
      <path d="M44 52h122" stroke={INK} strokeWidth="2" strokeDasharray="5 5" strokeOpacity=".6" />
      <g className="a-pop" style={d(900)}>
        <circle cx="172" cy="22" r="10" fill={PAPER} />
        <path d="M172 27v-10m-4.5 4.5 4.5-4.5 4.5 4.5" stroke={HOT} strokeWidth="2.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
      </g>
    </>
  );
}

function Shrink() {
  return (
    <>
      <path d="M40 100h124" stroke={INK} strokeOpacity=".3" strokeWidth="2" strokeLinecap="round" />
      <rect className="o-b a-grow" x="58" y="50" width="20" height="50" rx="4" fill={INK} fillOpacity=".28" />
      <rect className="o-b a-grow" style={d(90)} x="86" y="56" width="20" height="44" rx="4" fill={INK} fillOpacity=".28" />
      <rect className="o-b a-shrink" x="114" y="78" width="20" height="22" rx="4" fill="var(--positive)" />
      <path d="M44 56h122" stroke={INK} strokeWidth="2" strokeDasharray="5 5" strokeOpacity=".6" />
      <g className="a-pop" style={d(1000)}>
        <circle cx="124" cy="60" r="11" fill="var(--positive)" stroke={PAPER} strokeWidth="2.5" />
        <path d="m119 60 3.5 3.5 6.5-7" stroke={PAPER} strokeWidth="2.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
      </g>
      <path className="a-twinkle" d="M150 30q1.5 6 7 7.5-5.5 1.5-7 7.5-1.5-6-7-7.5 5.5-1.5 7-7.5z" fill={SUN} />
      <path className="a-twinkle" style={{ animationDelay: "1.2s, 2.2s" }} d="M164 52q1 3.5 4 4.5-3 1-4 4.5-1-3.5-4-4.5 3-1 4-4.5z" fill={SUN} />
    </>
  );
}

function Drain() {
  const id = useId();
  const glass = "M76 34h48l-7 66H83z";
  return (
    <>
      <clipPath id={id}>
        <path d={glass} />
      </clipPath>
      <g className="a-drop">
        <Coin x={100} y={18} />
      </g>
      <path d={glass} fill={PAPER} fillOpacity=".75" />
      <g clipPath={`url(#${id})`}>
        <rect className="o-b a-drain" x="70" y="80" width="60" height="20" fill={MINT} />
      </g>
      <path d={glass} fill="none" stroke={INK} strokeWidth="3" strokeLinejoin="round" />
      <path d="M118 42l-3 30" stroke={PAPER} strokeWidth="3" strokeLinecap="round" opacity=".8" />
      <path className="a-drip" d="M100 104q3 4 0 6.5-3-2.5 0-6.5z" fill={MINT_DARK} />
    </>
  );
}

function Piggy() {
  return (
    <>
      {[98, 90, 82].map((y, k) => (
        <g key={y} className="a-stack" style={d(k * 120)}>
          <ellipse cx="166" cy={y + 3} rx="14" ry="5" fill={SUN_EDGE} />
          <ellipse cx="166" cy={y} rx="14" ry="5" fill={SUN} stroke={SUN_EDGE} strokeWidth="1.5" />
        </g>
      ))}
      <g className="a-hop">
        <ellipse cx="166" cy="77" rx="14" ry="5" fill={SUN_EDGE} />
        <ellipse cx="166" cy="74" rx="14" ry="5" fill={SUN} stroke={SUN_EDGE} strokeWidth="1.5" />
      </g>
      <g className="a-pop">
        <path d="M126 52l8-12 4 15z" fill={MINT_DARK} />
        <rect x="94" y="92" width="9" height="12" rx="3" fill={MINT_DARK} />
        <rect x="124" y="92" width="9" height="12" rx="3" fill={MINT_DARK} />
        <ellipse cx="115" cy="74" rx="37" ry="27" fill={MINT} />
        <path d="M151 70q8-4 5 4" stroke={MINT_DARK} strokeWidth="2.5" fill="none" strokeLinecap="round" />
        <ellipse cx="80" cy="77" rx="8" ry="9" fill={MINT_DARK} />
        <circle cx="78" cy="74" r="1.6" fill={DEEP} />
        <circle cx="78" cy="80" r="1.6" fill={DEEP} />
        <circle cx="95" cy="66" r="2.6" fill={DEEP} />
        <rect x="104" y="47" width="22" height="4.5" rx="2.25" fill={DEEP} fillOpacity=".7" />
      </g>
    </>
  );
}

function Receipt() {
  const zig = "l-5.5 5-5.5-5-5.5 5-5.5-5-5.5 5-5.5-5-5.5 5-5.5-5";
  return (
    <>
      <g className="a-pop">
        <path d={`M78 14h44v58${zig}z`} fill={PAPER} stroke={INK} strokeWidth="2.5" strokeLinejoin="round" />
        {[
          [26, 30],
          [36, 22],
          [46, 28],
          [56, 18],
        ].map(([y, w]) => (
          <rect key={y} x={86} y={y} width={w} height="4" rx="2" fill={INK} fillOpacity=".3" />
        ))}
      </g>
      <g className="a-tear" style={{ transform: "translate(4px, 6px) rotate(10deg)" }}>
        <path d={`M122 80${zig}v24h44z`} fill={PAPER} stroke={INK} strokeWidth="2.5" strokeLinejoin="round" />
        <rect x="86" y="92" width="14" height="4" rx="2" fill={INK} fillOpacity=".3" />
        <rect x="104" y="91" width="12" height="6" rx="3" fill={HOT} />
      </g>
      <g className="a-fly">
        <Coin x={140} y={34} r={10} />
      </g>
    </>
  );
}

function Card() {
  return (
    <>
      <g className="a-slide">
        <rect x="46" y="30" width="104" height="64" rx="10" fill={DEEP} />
        <rect x="46" y="30" width="104" height="64" rx="10" fill="none" stroke={MINT} strokeOpacity=".35" strokeWidth="1.5" />
        <rect x="60" y="48" width="20" height="15" rx="3" fill={SUN} />
        <path d="M60 55.5h20M70 48v15" stroke={SUN_EDGE} strokeWidth="1.2" />
        {[60, 82, 104].map((x) => (
          <g key={x}>
            {[0, 5, 10, 15].map((dx) => (
              <circle key={dx} cx={x + dx} cy="78" r="1.8" fill="#eaf6f1" fillOpacity=".75" />
            ))}
          </g>
        ))}
        <path d="M132 46q4 5 0 10M137 43q6 8 0 16" stroke="#eaf6f1" strokeOpacity=".6" strokeWidth="2" fill="none" strokeLinecap="round" />
      </g>
      <g className="a-pop" style={d(500)}>
        <circle cx="150" cy="32" r="16" fill={SUN} stroke={PAPER} strokeWidth="3" />
        <text className="a-blink" x="150" y="33" textAnchor="middle" dominantBaseline="central" fontSize="20" fontWeight="800" fill={DEEP}>
          ?
        </text>
      </g>
    </>
  );
}

function Sunrise() {
  const id = useId();
  return (
    <>
      <clipPath id={id}>
        <rect width="200" height="80" />
      </clipPath>
      <g clipPath={`url(#${id})`}>
        <g className="a-rise">
          <g className="a-spin">
            {/* ponytail: endpoints via trig — a transform attr would fight the CSS transform-origin */}
            {Array.from({ length: 8 }, (_, k) => {
              const [c, s] = [Math.cos((k * Math.PI) / 4), Math.sin((k * Math.PI) / 4)];
              return <path key={k} d={`M${100 + 30 * c} ${82 + 30 * s}L${100 + 38 * c} ${82 + 38 * s}`} stroke={SUN} strokeWidth="4" strokeLinecap="round" />;
            })}
          </g>
          <circle cx="100" cy="82" r="22" fill={SUN} />
        </g>
      </g>
      <path d="M34 82h132" stroke={INK} strokeWidth="4" strokeLinecap="round" />
      <path className="a-grow" style={d(300)} d="M62 93h76M80 104h40" stroke={MINT_DARK} strokeWidth="4" strokeLinecap="round" />
    </>
  );
}

function FloatCoin() {
  return (
    <>
      <ellipse className="a-shadow" cx="100" cy="102" rx="20" ry="4" fill={INK} fillOpacity=".18" />
      <g className="a-float">
        <circle cx="100" cy="54" r="26" fill={SUN} stroke={SUN_EDGE} strokeWidth="3" />
        <circle cx="100" cy="54" r="19" fill="none" stroke={SUN_EDGE} strokeWidth="1.5" strokeOpacity=".7" />
        <text x="100" y="55" textAnchor="middle" dominantBaseline="central" fontSize="24" fontWeight="800" fill="#8a5d00">
          ₪
        </text>
      </g>
      <path className="a-twinkle" d="M138 26q1.5 6 7 7.5-5.5 1.5-7 7.5-1.5-6-7-7.5 5.5-1.5 7-7.5z" fill={SUN} />
    </>
  );
}

/** Finished cycle: income bar (green) above the expenses bar and a check, or expenses (red) over income and a "!". */
function Goal({ met }: { met: boolean }) {
  const [inc, exp] = met ? [70, 44] : [40, 70];
  return (
    <>
      <path d="M44 100h116" stroke={INK} strokeOpacity=".3" strokeWidth="2" strokeLinecap="round" />
      <rect className="o-b a-grow" x="70" y={100 - inc} width="24" height={inc} rx="4" fill={met ? "var(--positive)" : INK} fillOpacity={met ? 1 : 0.28} />
      <rect className={`o-b ${met ? "a-grow" : "a-spike"}`} style={d(150)} x="110" y={100 - exp} width="24" height={exp} rx="4" fill={met ? INK : HOT} fillOpacity={met ? 0.28 : 1} />
      <g className="a-pop" style={d(800)}>
        <circle cx={met ? 82 : 122} cy={100 - Math.max(inc, exp) - 14} r="12" fill={met ? "var(--positive)" : HOT} stroke={PAPER} strokeWidth="2.5" />
        {met ? (
          <path d={`m76 ${86 - inc} 4 4 7-7.5`} stroke={PAPER} strokeWidth="2.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
        ) : (
          <path d={`M122 ${80 - exp}v7m0 4.5v.5`} stroke={PAPER} strokeWidth="3" fill="none" strokeLinecap="round" />
        )}
      </g>
      {met && <path className="a-twinkle" d="M150 30q1.5 6 7 7.5-5.5 1.5-7 7.5-1.5-6-7-7.5 5.5-1.5 7-7.5z" fill={SUN} />}
    </>
  );
}

export function GoalIllustration({ met }: { met: boolean }) {
  return (
    <svg viewBox="36 0 132 108" className="ill ill-play size-full" aria-hidden="true" focusable="false">
      <Goal met={met} />
    </svg>
  );
}

const ART: Record<IllustrationName, () => React.ReactNode> = {
  spike: Spike,
  shrink: Shrink,
  drain: Drain,
  piggy: Piggy,
  receipt: Receipt,
  card: Card,
  sunrise: Sunrise,
  coin: FloatCoin,
};

export function Illustration({ name, active }: { name: IllustrationName; active: boolean }) {
  const Art = ART[name];
  return (
    <svg viewBox="16 4 172 116" className={`ill size-full ${active ? "ill-play" : ""}`} aria-hidden="true" focusable="false">
      <Art />
    </svg>
  );
}
