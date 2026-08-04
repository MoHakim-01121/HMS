// Baris kecil "kiriman billing terakhir" di halaman detail Invoice & Services.
import { useI18n } from "../../utils/i18n.jsx";

export default function LastBilling({ last }) {
  const { t } = useI18n();
  if (!last) return null;
  return (
    <div style={{ fontSize: 12, color: "var(--text-3)", margin: "0 0 12px" }}>
      {t("Last bill sent: {sent_at} to {target} ({status})", { sent_at: last.sent_at, target: last.target, status: last.status })}
    </div>
  );
}
