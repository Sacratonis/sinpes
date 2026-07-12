interface Props {
  invert: boolean;
  onChange: (invert: boolean) => void;
}

export default function ContrastToggle({ invert, onChange }: Props) {
  return (
    <div className="control-group">
      <span 
        onClick={() => onChange(true)} 
        style={{ cursor: 'pointer', color: invert ? 'var(--bg)' : 'var(--fg)' }}
      >
        ■
      </span>
      <span 
        onClick={() => onChange(false)} 
        style={{ cursor: 'pointer', color: invert ? 'var(--fg)' : 'var(--bg)' }}
      >
        □
      </span>
    </div>
  );
}