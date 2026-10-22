import { useI18n } from "../../utils/i18n.jsx";
import "../../styles/list-a.css";

// The list pages' empty block: a bold line and one sentence, no illustration.
// `iconName` is still accepted from older callers and ignored.
export default function EmptyState({ title, sub }) {
  const { t } = useI18n();
  return (
    <div className="la-empty">
      <b>{t(title)}</b>
      {sub && t(sub)}
    </div>
  );
}
