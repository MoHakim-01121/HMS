// Baris kecil "kiriman billing terakhir" di halaman detail Invoice & Services.
export default function LastBilling({ last }) {
  if (!last) return null;
  return (
    <div style={{ fontSize: 12, color: "var(--text-3)", margin: "0 0 12px" }}>
      Tagihan terakhir dikirim: {last.sent_at} ke {last.target} ({last.status})
    </div>
  );
}
