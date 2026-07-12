interface Weight {
  name: string;
  value: string;
}

interface Props {
  weights: Weight[] | null;
  activeWeight: string;
  onChange: (weight: string) => void;
}

export default function WeightToggle({ weights, activeWeight, onChange }: Props) {
  if (!weights) return null;

  return (
    <div className="weight-toggles">
      {weights.map(w => (
        <span 
          key={w.value} 
          className={activeWeight === w.value ? 'active' : ''}
          onClick={() => onChange(w.value)}
        >
          {w.name}
        </span>
      ))}
    </div>
  );
}