// Seksi halaman detail: label kapital kecil kiri, label kanan opsional
// (header kolom angka) atau aksi khusus di kanan.
export default function Section({ label, right, action, children }) {
  return (
    <div className="dv-sec">
      <div className="dv-sech">
        <span className="dv-l">{label}</span>
        {action || (right ? <span className="dv-l">{right}</span> : null)}
      </div>
      {children}
    </div>
  );
}
