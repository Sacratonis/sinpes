interface Props {
  size: number;
  onChange: (size: number) => void;
}

export default function SizeSlider({ size, onChange }: Props) {
  return (
    <div className="control-group">
      <span className="label-upper">Size</span>
      <input 
        type="range" 
        className="size-slider" 
        min="12" max="120" 
        value={size} 
        onInput={(e) => onChange(Number((e.target as HTMLInputElement).value))} 
      />
      <span className="tabular">{size}px</span>
    </div>
  );
}