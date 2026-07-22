// Kartu identitas mengambang yang menimpa hero (margin-top negatif).
// Slot kiri = children; slot kanan opsional (mis. boks Amount Due).
export default function FloatCard({ children, right }) {
  return (
    <div className="dv-float">
      <div className="dv-float-main">{children}</div>
      {right}
    </div>
  );
}
