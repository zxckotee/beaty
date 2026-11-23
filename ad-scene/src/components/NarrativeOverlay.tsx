import { STORY } from "../story";
import { overlayBlend } from "../timeline";

export function NarrativeOverlay({ timeMs }: { timeMs: number }) {
  const { from, to, mix } = overlayBlend(timeMs);
  const a = STORY[from];
  const b = STORY[to];

  return (
    <div className="ad-chrome">
      <div className="ad-brand-row">
        <img src="/beaty-welcome-hero.png" alt="Beaty-Welcome" className="ad-logo" />
        <p className="ad-brand">Beaty-Welcome</p>
      </div>
      <div className="ad-copy-stack">
        <h1 className="ad-title" style={{ opacity: 1 - mix }}>
          {a.title}
        </h1>
        <p className="ad-sub" style={{ opacity: 1 - mix }}>
          {a.subtitle}
        </p>
        {mix > 0 ? (
          <>
            <h1 className="ad-title ad-title--blend" style={{ opacity: mix }}>
              {b.title}
            </h1>
            <p className="ad-sub ad-sub--blend" style={{ opacity: mix }}>
              {b.subtitle}
            </p>
          </>
        ) : null}
      </div>
      <p className="ad-beat-pill">{mix > 0.5 ? b.label : a.label}</p>
    </div>
  );
}