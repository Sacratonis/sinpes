interface Props {
  label: string;
  text: string;
  sizeClass: "spec-32" | "spec-16" | "spec-12";
  weight: string;
}

export default function SpecimenRow({ label, text, sizeClass, weight }: Props) {
  return (
    <div className="specimen-row">
      <span className="label-upper">{label}</span>
      <div className={sizeClass} style={{ fontWeight: weight }}>
        {text}
      </div>
    </div>
  );
}