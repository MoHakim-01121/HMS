// List-page header (Homlu v2.1): title, an optional line under it, and the
// page's actions on the right. `title` and `sub` are already-translated
// nodes/strings. Phones get an 18px title and no action buttons (doc 02d).
export default function PageHeader({ title, sub, actions }) {
  return (
    <div className="mb-6 flex flex-wrap items-start justify-between gap-4 max-[600px]:mb-3.5">
      <div className="min-w-0">
        <div className="text-[21px] leading-[1.15] font-semibold tracking-[-.02em] text-foreground max-[600px]:text-[18px]">{title}</div>
        {sub && <div className="mt-1 text-[12.5px] leading-normal text-muted-foreground">{sub}</div>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2 max-[600px]:hidden">{actions}</div>}
    </div>
  );
}
