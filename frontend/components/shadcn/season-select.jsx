import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./ui/select.jsx";
import { useI18n } from "../../utils/i18n.jsx";

// Picks an umrah season (Finance → Periods) for a report's date range. Shows
// the season whose dates the report is on, else the placeholder; hidden while
// no season exists.
export default function SeasonSelect({ seasons = [], dateFrom, dateTo, onPick, className = "w-44" }) {
  const { t } = useI18n();
  if (!seasons.length) return null;
  const current = seasons.find((s) => s.date_from === dateFrom && s.date_to === dateTo);
  return (
    <Select
      value={current ? String(current.id) : ""}
      onValueChange={(v) => {
        const s = seasons.find((x) => String(x.id) === v);
        if (s) onPick(s.date_from, s.date_to);
      }}
    >
      <SelectTrigger className={className} style={{ height: 40 }} aria-label={t("Season")}>
        <SelectValue placeholder={t("Season")} />
      </SelectTrigger>
      <SelectContent>
        {seasons.map((s) => <SelectItem key={s.id} value={String(s.id)}>{s.name}</SelectItem>)}
      </SelectContent>
    </Select>
  );
}
