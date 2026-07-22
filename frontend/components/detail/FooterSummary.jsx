// Blok penutup halaman detail: dua kolom di atas garis
// (kiri mis. "PAID", kanan total besar). Kolom kiri boleh kosong.
export default function FooterSummary({ left, right }) {
  return (
    <div className="dv-sec">
      <div className="dv-foot">
        <div style={{ flex: 1 }}>{left}</div>
        <div style={{ textAlign: "right" }}>{right}</div>
      </div>
    </div>
  );
}
