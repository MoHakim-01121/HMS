import { Fragment } from "react";
import { Icon } from "../icons.jsx";
import { Button } from "./ui/button.jsx";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "./ui/dropdown-menu.jsx";
import { useI18n } from "../../utils/i18n.jsx";

// The "Export ▾" affordance on list pages, built on the shared Radix dropdown
// so it gets keyboard navigation, collision-aware positioning and the same
// look as every other menu in the app.
//
//   items: [{ href, label, hint?, external? }]
//
// Items are grouped by file format (read from the href): spreadsheet first,
// then PDF, with a divider between them. A group with more than one item gets
// a heading so the choices inside it read as variants of one format.
const FORMATS = {
  csv: { icon: "file-text", title: "Spreadsheet" },
  pdf: { icon: "pdf", title: "PDF" },
};

const formatOf = (href) => (/csv/i.test(href) ? "csv" : "pdf");

export default function ExportMenu({ items, label }) {
  const { t } = useI18n();
  const groups = ["csv", "pdf"]
    .map((fmt) => ({ fmt, items: items.filter((it) => formatOf(it.href) === fmt) }))
    .filter((g) => g.items.length);

  return (
    // modal={false}: a modal Radix menu locks body scroll, which fights this
    // app's sidebar padding on <body> and shifts the page (see kebab-menu.jsx).
    <DropdownMenu modal={false}>
      <DropdownMenuTrigger asChild>
        <Button
          type="button"
          variant="outline"
          size="lg"
          // Neutral hover/open/focus: the outline variant tints its border with
          // --ring (gold), which read as a stuck yellow focus while the menu
          // was open under the cursor.
          className="group export-dropdown hover:border-input hover:bg-muted data-[state=open]:bg-muted focus-visible:border-input focus-visible:ring-foreground/15"
        >
          <Icon name="download" size={15} />
          {label || t("Export")}
          <Icon
            name="chevron"
            size={14}
            className="text-muted-foreground transition-transform duration-200 ease-[cubic-bezier(0.2,0,0,1)] group-data-[state=open]:rotate-180"
          />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-[200px]">
        {groups.map((g, gi) => (
          <Fragment key={g.fmt}>
            {gi > 0 && <DropdownMenuSeparator />}
            {g.items.length > 1 && (
              <DropdownMenuLabel className="text-xs font-medium text-muted-foreground">
                {t(FORMATS[g.fmt].title)}
              </DropdownMenuLabel>
            )}
            {g.items.map((it) => (
              <DropdownMenuItem key={it.href} asChild className={it.hint ? "items-start" : undefined}>
                <a href={it.href} {...(it.external ? { target: "_blank", rel: "noreferrer" } : {})}>
                  <Icon name={FORMATS[g.fmt].icon} size={15} className={it.hint ? "mt-0.5" : undefined} />
                  <span className="flex flex-col gap-0.5">
                    <span className="whitespace-nowrap">{it.label}</span>
                    {it.hint && <span className="text-xs text-muted-foreground">{it.hint}</span>}
                  </span>
                </a>
              </DropdownMenuItem>
            ))}
          </Fragment>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
