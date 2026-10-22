import { useI18n } from "../../utils/i18n.jsx";
import { Empty } from "./list-a.jsx";

// The list pages' empty block: a bold line and one sentence, no illustration.
// `iconName` is still accepted from older callers and ignored.
export default function EmptyState({ title, sub }) {
  const { t } = useI18n();
  return <Empty title={t(title)} sub={sub && t(sub)} />;
}
