import { Icon } from "../icons.jsx";
import { useI18n } from "../../utils/i18n.jsx";
import { cn } from "@/lib/utils";

// Search pill for a panel's own toolbar: icon, input and a clear button.
// The list pages search through list-a's Toolbar instead.
export default function SearchBox({ value, onChange, placeholder, className }) {
  const { t } = useI18n();
  return (
    <div className={cn(
      "flex h-[38px] min-w-[180px] flex-1 items-center gap-2.5 rounded-full border border-input bg-card px-3.5 transition-[border-color] duration-150 focus-within:border-foreground",
      "phone:h-11 phone:min-w-0",
      className,
    )}>
      <Icon name="search" size={13} className="shrink-0 text-muted-foreground" />
      <input
        type="text"
        value={value}
        placeholder={t(placeholder)}
        onChange={(e) => onChange(e.target.value)}
        className="size-full rounded-none border-0 bg-transparent p-0 font-[inherit] text-[13px] text-foreground shadow-none outline-none placeholder:text-muted-foreground focus:shadow-none phone:text-[16px]"
      />
      {value && (
        <button type="button" title={t("Clear search")} onClick={() => onChange("")}
          className="inline-flex size-5 shrink-0 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground">
          <Icon name="close" size={11} strokeWidth={2.5} />
        </button>
      )}
    </div>
  );
}
