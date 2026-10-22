import { useState } from "react";
import { router } from "@inertiajs/react";
import { ListPage, Toolbar, Primary, TableCard, Section, RowMenu, Pill, Empty, dLong, rowNav, Tr, Th, Td, Note, ToolButton } from "../../components/shadcn/list-a.jsx";
import { useConfirm } from "../../components/shadcn/confirm-dialog.jsx";
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "../../components/shadcn/ui/dialog.jsx";
import { Input } from "../../components/shadcn/ui/input.jsx";
import { Button } from "../../components/shadcn/ui/button.jsx";
import FormField from "../../components/shadcn/form-field.jsx";
import { useI18n } from "../../utils/i18n.jsx";
import { usePerms } from "../../utils/perms.js";

// Financial periods: the umrah seasons (for reports) and the monthly
// periods the books close by. Dialogs create periods and edit seasons.
export default function List({ periods = [], seasons = [], next_season = null }) {
  const { t } = useI18n();
  const perms = usePerms();
  const canManage = perms.can("periods", "edit");
  const [confirm, confirmDialog] = useConfirm();
  const [createDialog, setCreateDialog] = useState(false);
  const [year, setYear] = useState(new Date().getFullYear());
  const [season, setSeason] = useState(null); // {id?, name, date_from, date_to} while the dialog is open

  const saveSeason = () => {
    const { id, ...data } = season;
    router.post(id ? `/finance/seasons/${id}/edit/` : "/finance/seasons/create/", data, {
      // A refused season comes back as an error flash: keep the dialog and its input.
      onSuccess: (page) => { if (!page.props.flash?.error) setSeason(null); },
    });
  };
  // Calendar months a season spans — the periods it closes by.
  const monthsIn = (s) => {
    const [fy, fm] = s.date_from.split("-").map(Number);
    const [ty, tm] = s.date_to.split("-").map(Number);
    return (ty - fy) * 12 + (tm - fm) + 1;
  };

  const createPeriods = () => {
    router.post("/finance/periods/create/", { year });
    setCreateDialog(false);
  };

  const STATUS_TONE = { open: "green", soft_close: "amber", closed: "amber-o", locked: "gray" };
  const periodMenu = (p) => [
    canManage && p.is_postable && { label: t("Close period"), onClick: () => confirm({ title: t("Close Period"), message: t("Close this period?"), onConfirm: () => router.post(`/finance/periods/${p.id}/close/`) }) },
    canManage && p.status === "closed" && { label: t("Lock period"), danger: true, onClick: () => confirm({ title: t("Lock Period"), message: t("Lock this period? This is irreversible."), onConfirm: () => router.post(`/finance/periods/${p.id}/lock/`) }) },
  ];

  return (
    <ListPage title={t("Financial Periods")}>
      <Toolbar left={<Note>{t("Books close month by month; a season groups its months for reporting.")}</Note>}>
        {canManage && <ToolButton onClick={() => setCreateDialog(true)}>{t("Create periods")}</ToolButton>}
        {canManage && <Primary label={t("New season")} onClick={() => setSeason({ name: "", date_from: "", date_to: "", ...(next_season || {}) })} />}
      </Toolbar>

      <Section title={t("Umrah seasons")} />
      <TableCard cols={[null, 260, 100, 56]}
        empty={!seasons.length && <Empty title={t("No seasons yet")} sub={t("Add a season with its start and end date to read reports for the whole season.")} />}>
        <thead><Tr><Th>{t("Season")}</Th><Th>{t("Dates")}</Th><Th className="text-right">{t("Months")}</Th><Th className="text-center">{t("Action")}</Th></Tr></thead>
        <tbody>
          {seasons.map((s) => (
            <Tr key={s.id} row="static">
              <Td className="font-medium">{s.name}</Td>
              <Td>{dLong(s.date_from)} – {dLong(s.date_to)}</Td>
              <Td className="text-right">{monthsIn(s)}</Td>
              <Td className="text-center">
                {canManage && <RowMenu label={t("Actions for {n}", { n: s.name })} items={[
                  { label: t("Edit"), onClick: () => setSeason({ ...s }) },
                  { label: t("Delete"), danger: true, onClick: () => confirm({ title: t("Delete Season"), message: t("Delete this season? Its monthly periods and journal entries stay as they are."), onConfirm: () => router.post(`/finance/seasons/${s.id}/delete/`) }) },
                ]} />}
              </Td>
            </Tr>
          ))}
        </tbody>
      </TableCard>

      <Section title={t("Monthly periods")} />
      <TableCard cols={[120, 130, null, 140, 120, 56]}
        empty={!periods.length && <Empty title={t("No periods yet")} sub={t("Create periods to generate the twelve months of a year.")} />}>
        <thead><Tr>
          <Th>{t("Period")}</Th><Th>{t("Status")}</Th><Th>{t("Dates")}</Th>
          <Th className="text-right">{t("Journal entries")}</Th><Th className="text-right">{t("Payments")}</Th><Th className="text-center">{t("Action")}</Th>
        </Tr></thead>
        <tbody>
          {periods.map((p) => (
            <Tr key={p.id} {...rowNav(`/finance/periods/${p.id}/`)}>
              <Td className="font-medium">{p.name}</Td>
              <Td><Pill tone={STATUS_TONE[p.status] || "gray"}>{p.status_display}</Pill></Td>
              <Td>{dLong(p.date_from)} – {dLong(p.date_to)}</Td>
              <Td className={"text-right" + (p.journal_count ? "" : " text-muted-foreground")}>{p.journal_count}</Td>
              <Td className={"text-right" + (p.payment_count ? "" : " text-muted-foreground")}>{p.payment_count}</Td>
              <Td className="text-center"><RowMenu label={t("Actions for {n}", { n: p.name })} items={periodMenu(p)} /></Td>
            </Tr>
          ))}
        </tbody>
      </TableCard>

      {/* Create Periods Dialog */}
      {createDialog && (
        <Dialog open onOpenChange={(v) => { if (!v) setCreateDialog(false); }}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>{t("Create Financial Periods")}</DialogTitle>
            </DialogHeader>
            <p className="text-sm text-muted-foreground mb-4">
              {t("Create 12 monthly periods for the selected year.")}
            </p>
            <div className="flex items-center gap-2">
              <label className="text-sm font-medium">{t("Year")}:</label>
              <Input
                type="number"
                value={year}
                onChange={(e) => setYear(parseInt(e.target.value) || new Date().getFullYear())}
                className="w-24"
              />
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setCreateDialog(false)}>{t("Cancel")}</Button>
              <Button onClick={createPeriods}>{t("Create")}</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
      {season && (
        <Dialog open onOpenChange={(v) => { if (!v) setSeason(null); }}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>{season.id ? t("Edit Season") : t("New Season")}</DialogTitle>
            </DialogHeader>
            <form
              className="flex flex-col gap-4"
              onSubmit={(e) => { e.preventDefault(); saveSeason(); }}
            >
              <FormField label={t("Name")} name="season_name" required autoFocus
                value={season.name} placeholder={t("e.g. Season 1448H")}
                onChange={(v) => setSeason((s) => ({ ...s, name: v }))} />
              <div className="grid grid-cols-2 gap-3">
                <FormField label={t("Start")} name="season_from" type="date" required
                  value={season.date_from} onChange={(v) => setSeason((s) => ({ ...s, date_from: v }))} />
                <FormField label={t("End")} name="season_to" type="date" required min={season.date_from || undefined}
                  value={season.date_to} onChange={(v) => setSeason((s) => ({ ...s, date_to: v }))} />
              </div>
              {!season.id && next_season ? (
                <p className="text-sm text-muted-foreground">{t("Filled in from the Umm al-Qura calendar: the season opens on 14 Dhul Hijjah, right after Hajj, and runs until the next one opens. Change the dates if your season differs.")}</p>
              ) : null}
              <p className="text-sm text-muted-foreground">{t("Monthly periods missing in this range are created for you.")}</p>
              <DialogFooter>
                <Button type="button" variant="outline" onClick={() => setSeason(null)}>{t("Cancel")}</Button>
                <Button type="submit" disabled={!season.name.trim() || !season.date_from || !season.date_to}>{t("Save")}</Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>
      )}
      {confirmDialog}
    </ListPage>
  );
}
