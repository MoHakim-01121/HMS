import { useState } from "react";
import { router } from "@inertiajs/react";
import PageBack from "../../components/shadcn/page-back.jsx";
import PageHeader from "../../components/shadcn/page-header.jsx";
import DetailTable from "../../components/shadcn/detail-table.jsx";
import StatusPill from "../../components/shadcn/status-pill.jsx";
import RowActions from "../../components/shadcn/row-actions.jsx";
import EmptyState from "../../components/shadcn/empty-state.jsx";
import FormField from "../../components/shadcn/form-field.jsx";
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "../../components/shadcn/ui/dialog.jsx";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "../../components/shadcn/ui/select.jsx";
import { Textarea } from "../../components/shadcn/ui/textarea.jsx";
import { Input } from "../../components/shadcn/ui/input.jsx";
import { Button } from "../../components/shadcn/ui/button.jsx";
import { useConfirm } from "../../components/shadcn/confirm-dialog.jsx";
import { useI18n } from "../../utils/i18n.jsx";
import { usePerms } from "../../utils/perms.js";

const STATUS_TONE = {
  open: "yellow",
  partially_settled: "blue",
  settled: "green",
  cancelled: "gray",
};

const EMPTY_OBLIGATION = { branch: "", amount_sar: "", due_date: "", note: "" };
const EMPTY_SETTLEMENT = { remittance: "", received_amount_sar: "", received_date: new Date().toISOString().split("T")[0], reference: "", note: "" };

export default function List({ obligations = [], settlements = [], pending_diff = [], branch_choices = [], remittance_choices = [] }) {
  const { t } = useI18n();
  const perms = usePerms();
  const canEdit = perms.can("remittance", "edit");
  const [confirm, confirmDialog] = useConfirm();

  const closeDiff = (row) => {
    confirm({
      title: t("Close Difference"),
      message: t("Book the {n} SAR difference for {remittance} as a bank fee/FX gain? This cannot be edited afterwards — only reversed.", {
        n: Math.abs(row.diff_sar).toLocaleString(), remittance: row.remittance_number,
      }),
      danger: true,
      onConfirm: () => router.post(`/remittance/settlement/remittances/${row.id}/close-diff/`),
    });
  };

  const [obDialog, setObDialog] = useState(false);
  const [obForm, setObForm] = useState({ ...EMPTY_OBLIGATION });
  const [stDialog, setStDialog] = useState(false);
  const [stForm, setStForm] = useState({ ...EMPTY_SETTLEMENT });
  const [allocSettlement, setAllocSettlement] = useState(null);
  const [allocRows, setAllocRows] = useState({});

  const openObligations = obligations.filter((o) => o.status === "open" || o.status === "partially_settled");

  const submitObligation = () => {
    router.post("/remittance/settlement/obligations/new/", obForm, {
      onSuccess: () => { setObDialog(false); setObForm({ ...EMPTY_OBLIGATION }); },
    });
  };

  const submitSettlement = () => {
    router.post("/remittance/settlement/new/", stForm, {
      onSuccess: () => { setStDialog(false); setStForm({ ...EMPTY_SETTLEMENT }); },
    });
  };

  const openAllocate = (s) => {
    setAllocSettlement(s);
    setAllocRows({});
  };

  const allocTotal = Object.values(allocRows).reduce((sum, v) => sum + (Number(v) || 0), 0);

  const submitAllocate = () => {
    const rows = Object.entries(allocRows)
      .filter(([, amt]) => Number(amt) > 0)
      .map(([obligation_id, amount_sar]) => ({ obligation_id: Number(obligation_id), amount_sar: Number(amount_sar) }));
    if (!rows.length) return;
    router.post(`/remittance/settlement/${allocSettlement.id}/allocate/`, {
      allocations: JSON.stringify(rows),
    }, {
      onSuccess: () => setAllocSettlement(null),
    });
  };

  const obligationColumns = [
    { header: t("Branch"), render: (o) => o.branch_name },
    { header: t("Reservation"), render: (o) => o.reservation_number || "—" },
    { header: t("Status"), render: (o) => <StatusPill tone={STATUS_TONE[o.status] || "gray"} label={o.status_display} /> },
    { header: t("Amount (SAR)"), align: "right", render: (o) => o.amount_sar?.toLocaleString() },
    { header: t("Settled (SAR)"), align: "right", render: (o) => o.settled_sar?.toLocaleString() },
    { header: t("Outstanding (SAR)"), align: "right", render: (o) => o.outstanding_sar?.toLocaleString() },
    { header: t("Due"), render: (o) => o.due_date || "—" },
  ];

  const settlementColumns = [
    { header: t("Remittance"), render: (s) => s.remittance_number },
    { header: t("Date"), render: (s) => s.received_date },
    { header: t("Received (SAR)"), align: "right", render: (s) => s.received_amount_sar?.toLocaleString() },
    { header: t("Allocated (SAR)"), align: "right", render: (s) => s.allocated_sar?.toLocaleString() },
    { header: t("Unallocated (SAR)"), align: "right", render: (s) => s.unallocated_sar?.toLocaleString() },
    { header: t("Reference"), render: (s) => s.reference || "—" },
    {
      header: "",
      render: (s) => (
        canEdit && s.unallocated_sar > 0 ? (
          <RowActions actions={[{ icon: "arrow-right", label: t("Allocate"), onClick: () => openAllocate(s) }]} />
        ) : null
      ),
    },
  ];

  return (
    <div className="page shadcn-root">
      <PageBack label={t("Back")} />

      <PageHeader
        title={t("HQ Settlement")}
        sub={t("Track branch obligations and how much HQ has actually received.")}
        actions={
          canEdit ? (
            <>
              <Button variant="outline" size="lg" onClick={() => setObDialog(true)}>{t("New Obligation")}</Button>
              <Button size="lg" onClick={() => setStDialog(true)}>{t("New Settlement")}</Button>
            </>
          ) : null
        }
      />

      {pending_diff.length > 0 && (
        <div className="hms-list-card" style={{ marginBottom: 24 }}>
          <div style={{ padding: "16px 20px 0", fontWeight: 600, fontSize: 14 }}>{t("Pending Reconciliation")}</div>
          <DetailTable
            columns={[
              { header: t("Remittance"), render: (r) => r.remittance_number },
              { header: t("Expected (SAR)"), align: "right", render: (r) => r.expected_sar?.toLocaleString() },
              { header: t("Received (SAR)"), align: "right", render: (r) => r.received_total_sar?.toLocaleString() },
              {
                header: t("Difference (SAR)"), align: "right",
                render: (r) => (
                  <span style={{ color: r.diff_sar > 0 ? "var(--yellow)" : "var(--green)" }}>
                    {r.diff_sar > 0 ? "−" : "+"}{Math.abs(r.diff_sar).toLocaleString()}
                  </span>
                ),
              },
              {
                header: "",
                render: (r) => (
                  canEdit ? (
                    <RowActions actions={[{ icon: "check", label: t("Close Difference"), onClick: () => closeDiff(r) }]} />
                  ) : null
                ),
              },
            ]}
            rows={pending_diff}
            rowKey={(r) => r.id}
          />
        </div>
      )}

      <div className="hms-list-card">
        <div style={{ padding: "16px 20px 0", fontWeight: 600, fontSize: 14 }}>{t("Obligations")}</div>
        {obligations.length > 0 ? (
          <DetailTable columns={obligationColumns} rows={obligations} rowKey={(o) => o.id} />
        ) : (
          <EmptyState iconName="wallet" title={t("No obligations found")} sub={t("No branch owes HQ anything right now.")} />
        )}
      </div>

      <div className="hms-list-card" style={{ marginTop: 24 }}>
        <div style={{ padding: "16px 20px 0", fontWeight: 600, fontSize: 14 }}>{t("Settlements")}</div>
        {settlements.length > 0 ? (
          <DetailTable columns={settlementColumns} rows={settlements} rowKey={(s) => s.id} />
        ) : (
          <EmptyState iconName="wallet" title={t("No settlements found")} sub={t("No remittance has been received yet.")} />
        )}
      </div>

      {obDialog && (
        <Dialog open onOpenChange={(v) => { if (!v) setObDialog(false); }}>
          <DialogContent className="hms-dialog">
            <DialogHeader><DialogTitle>{t("New Obligation")}</DialogTitle></DialogHeader>
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              <FormField label={t("Branch")} name="branch" required>
                <Select value={obForm.branch} onValueChange={(v) => setObForm({ ...obForm, branch: v })}>
                  <SelectTrigger className="w-full"><SelectValue placeholder={t("Select branch...")} /></SelectTrigger>
                  <SelectContent>
                    {branch_choices.map((b) => <SelectItem key={b.value} value={b.value}>{b.label}</SelectItem>)}
                  </SelectContent>
                </Select>
              </FormField>
              <FormField label={t("Amount (SAR)")} name="amount_sar" type="number" required
                value={obForm.amount_sar} onChange={(v) => setObForm({ ...obForm, amount_sar: v })} />
              <FormField label={t("Due Date")} name="due_date" type="date"
                value={obForm.due_date} onChange={(v) => setObForm({ ...obForm, due_date: v })} />
              <FormField label={t("Note")} name="note">
                <Textarea rows={2} value={obForm.note} onChange={(e) => setObForm({ ...obForm, note: e.target.value })} />
              </FormField>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setObDialog(false)}>{t("Cancel")}</Button>
              <Button onClick={submitObligation} disabled={!obForm.branch || !obForm.amount_sar}>{t("Save")}</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}

      {stDialog && (
        <Dialog open onOpenChange={(v) => { if (!v) setStDialog(false); }}>
          <DialogContent className="hms-dialog">
            <DialogHeader><DialogTitle>{t("New Settlement")}</DialogTitle></DialogHeader>
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              <FormField label={t("Remittance")} name="remittance" required>
                <Select value={stForm.remittance} onValueChange={(v) => setStForm({ ...stForm, remittance: v })}>
                  <SelectTrigger className="w-full"><SelectValue placeholder={t("Select remittance...")} /></SelectTrigger>
                  <SelectContent>
                    {remittance_choices.map((r) => <SelectItem key={r.value} value={String(r.value)}>{r.label}</SelectItem>)}
                  </SelectContent>
                </Select>
              </FormField>
              <FormField label={t("Received Amount (SAR)")} name="received_amount_sar" type="number" required
                value={stForm.received_amount_sar} onChange={(v) => setStForm({ ...stForm, received_amount_sar: v })} />
              <FormField label={t("Received Date")} name="received_date" type="date" required
                value={stForm.received_date} onChange={(v) => setStForm({ ...stForm, received_date: v })} />
              <FormField label={t("Reference")} name="reference"
                value={stForm.reference} onChange={(v) => setStForm({ ...stForm, reference: v })} />
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setStDialog(false)}>{t("Cancel")}</Button>
              <Button onClick={submitSettlement} disabled={!stForm.remittance || !stForm.received_amount_sar}>{t("Save")}</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}

      {allocSettlement && (
        <Dialog open onOpenChange={(v) => { if (!v) setAllocSettlement(null); }}>
          <DialogContent className="hms-dialog">
            <DialogHeader><DialogTitle>{t("Allocate Settlement")}</DialogTitle></DialogHeader>
            <p className="text-sm text-muted-foreground">
              {t("{n} SAR unallocated from {remittance}.", { n: allocSettlement.unallocated_sar?.toLocaleString(), remittance: allocSettlement.remittance_number })}
            </p>
            <div style={{ display: "flex", flexDirection: "column", gap: 10, maxHeight: 320, overflowY: "auto" }}>
              {openObligations.length === 0 ? (
                <span className="text-sm text-muted-foreground">{t("No open obligations to allocate to.")}</span>
              ) : openObligations.map((o) => (
                <div key={o.id} style={{ display: "grid", gridTemplateColumns: "1fr 120px", gap: 10, alignItems: "center" }}>
                  <span className="text-sm">{o.branch_name} — {t("outstanding")} {o.outstanding_sar?.toLocaleString()} SAR</span>
                  <Input
                    type="number" placeholder="0" min="0" max={o.outstanding_sar}
                    value={allocRows[o.id] || ""}
                    onChange={(e) => setAllocRows({ ...allocRows, [o.id]: e.target.value })}
                  />
                </div>
              ))}
            </div>
            <div style={{ textAlign: "right", fontSize: 13, fontWeight: 600 }}>
              {t("Total")}: {allocTotal.toLocaleString()} / {allocSettlement.unallocated_sar?.toLocaleString()} SAR
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setAllocSettlement(null)}>{t("Cancel")}</Button>
              <Button onClick={submitAllocate} disabled={allocTotal <= 0 || allocTotal > allocSettlement.unallocated_sar}>
                {t("Allocate")}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}

      {confirmDialog}
    </div>
  );
}
