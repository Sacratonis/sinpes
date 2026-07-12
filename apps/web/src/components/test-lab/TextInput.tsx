interface Props {
  text: string;
  size: number;
  weight: string;
  onChange: (text: string) => void;
}

export default function TextInput({ text, size, weight, onChange }: Props) {
  return (
    <div className="test-canvas">
      <textarea 
        className="canvas-input" 
        rows={2} 
        spellcheck={false}
        style={{ fontSize: `${size}px`, fontWeight: weight }}
        value={text} 
        onInput={(e) => onChange((e.target as HTMLTextAreaElement).value)}
      />
    </div>
  );
}