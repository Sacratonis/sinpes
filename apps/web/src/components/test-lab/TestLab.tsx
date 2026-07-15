import { useState } from 'preact/hooks';

interface Weight { name: string; value: string; }
interface TestLabProps {
  fontName: string;
  fontSlug: string;
  woff2Url?: string;
  initialText?: string;
  weights?: Weight[] | null;
  translations: {
    size: string;
    display: string;
    body: string;
    caption: string;
    weight: string;
    editHint: string;
    specimenDisplay: string;
    specimenBody: string;
    specimenCaption: string;
  };
}

export default function TestLab({
  fontName,
  fontSlug,
  woff2Url,
  initialText = 'The quick brown fox jumps over the lazy dog.',
  weights = [
    { name: 'Regular', value: '400' },
    { name: 'Medium', value: '500' },
    { name: 'Bold', value: '700' },
  ],
  translations,
}: TestLabProps) {
  const [size, setSize] = useState(64);
  const [text, setText] = useState(initialText);
  const [activeWeight, setActiveWeight] = useState(weights ? weights[0].value : '400');
  const [focused, setFocused] = useState(false);

  const fontStyle = { fontFamily: `"${fontName}", 'IBM Plex Sans', sans-serif`, fontWeight: activeWeight };

  return (
    <div className="lab-wrapper">

      {/* ── STICKY TOOLBAR ── */}
      <div className="lab-toolbar">
        {/* Size control */}
        <div className="toolbar-group">
          <span className="toolbar-label">{translations.size}</span>
          <input
            type="range"
            className="lab-slider"
            min="12" max="160"
            aria-label={translations.size}
            value={size}
            onInput={(e) => setSize(Number((e.target as HTMLInputElement).value))}
          />
          <span className="toolbar-readout">{size}px</span>
        </div>

        {/* Weight toggles */}
        {weights && weights.length > 0 && (
          <div className="toolbar-group">
            <span className="toolbar-label">{translations.weight}</span>
            <div className="weight-pills">
              {weights.map(w => (
                <button
                  key={w.value}
                  className={`weight-pill${activeWeight === w.value ? ' active' : ''}`}
                  aria-pressed={activeWeight === w.value}
                  onClick={() => setActiveWeight(w.value)}
                >
                  {w.name}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* ── LIVE CANVAS ── */}
      <div className="lab-canvas">
        {!focused && text === initialText && (
          <span className="canvas-hint">{translations.editHint}</span>
        )}
        <textarea
          className="canvas-input"
          aria-label={translations.editHint}
          rows={3}
          spellcheck={false}
          style={{ ...fontStyle, fontSize: `${size}px` }}
          value={text}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          onInput={(e) => setText((e.target as HTMLTextAreaElement).value)}
        />
      </div>

      {/* ── SPECIMEN TABLE ── */}
      <div className="specimen-table">

        <div className="specimen-row">
          <div className="specimen-meta">
            <span className="spec-label">{translations.display}</span>
            <span className="spec-size">32px</span>
          </div>
          <div className="specimen-text spec-32" style={fontStyle}>
            {translations.specimenDisplay}
          </div>
        </div>

        <div className="specimen-row">
          <div className="specimen-meta">
            <span className="spec-label">{translations.body}</span>
            <span className="spec-size">16px</span>
          </div>
          <div className="specimen-text spec-16" style={fontStyle}>
            {translations.specimenBody}
          </div>
        </div>

        <div className="specimen-row">
          <div className="specimen-meta">
            <span className="spec-label">{translations.caption}</span>
            <span className="spec-size">12px</span>
          </div>
          <div className="specimen-text spec-12" style={fontStyle}>
            {translations.specimenCaption}
          </div>
        </div>

      </div>
    </div>
  );
}
