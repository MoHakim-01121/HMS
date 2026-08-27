import { Icon } from "../icons.jsx";
import { useI18n } from "../../utils/i18n.jsx";

export default function EmptyState({ title, sub, iconName }) {
  const { t } = useI18n();
  return (
    <div className="empty">
      {iconName && <Icon name={iconName} size={36} strokeWidth={1.5} />}
      <div className="empty-title">{t(title)}</div>
      {sub && <div className="empty-sub">{t(sub)}</div>}
    </div>
  );
}
