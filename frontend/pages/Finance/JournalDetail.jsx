import { DPage, DTop, DHead, DCard } from "../../components/shadcn/detail-a.jsx";
import { useI18n } from "../../utils/i18n.jsx";
import { fmt, fmtDate } from "../../utils/format.js";

// Journal entry detail, in the detail-page language of the Record View HMS
// canvas (no artboard of its own): the head card with the entry's facts, then
// its lines with debit and credit totals.
export default function JournalDetail({ entry = {}, created_by = "", reverses_number = null, lines = [] }) {
  const { t } = useI18n();
  const totalDebit = lines.reduce((s, l) => s + (l.amount_sar > 0 ? l.amount_sar : 0), 0);
  const totalCredit = lines.reduce((s, l) => s + (l.amount_sar < 0 ? -l.amount_sar : 0), 0);
  const balanced = totalDebit === totalCredit;

  return (
    <DPage>
      <DTop href="/finance/journal/" />

      <DHead
        title={entry.entry_number}
        badge={entry.is_reversal ? { label: t("Reversal"), tone: "red" } : { label: t(entry.entry_type_display), tone: "gray" }}
        facts={[
          { k: t("Type"), v: t(entry.entry_type_display) },
          { k: t("Date"), v: fmtDate(entry.entry_date) || t("Not set") },
          { k: t("Created by"), v: created_by || t("System") },
          reverses_number && { k: t("Reverses"), v: <a href={`/finance/journal/?q=${encodeURIComponent(reverses_number)}`}>{reverses_number}</a> },
          { k: t("Total"), v: `${fmt(totalDebit)} SAR`, strong: true, tone: balanced ? undefined : "danger" },
        ]}
        note={entry.description ? { label: t("Description"), text: entry.description } : null}
      />

      <DCard title={t("Lines")} count={lines.length} meta={t("Amounts in SAR")}>
        <div className="da-scroll">
          <table className="da-t">
            <thead><tr><th>{t("Account")}</th><th>{t("Reference")}</th><th>{t("Note")}</th><th className="n w">{t("Debit")}</th><th className="n w">{t("Credit")}</th></tr></thead>
            <tbody>
              {lines.length ? lines.map((l) => (
                <tr key={l.id}>
                  <td className="strong" style={{ whiteSpace: "nowrap" }}>{l.account_display}</td>
                  <td className="mut">{l.dim || ""}</td>
                  <td className="mut">{l.note || ""}{l.native ? <span className="sub">{l.native}</span> : null}</td>
                  <td className="n">{l.amount_sar > 0 ? fmt(l.amount_sar) : ""}</td>
                  <td className="n">{l.amount_sar < 0 ? fmt(-l.amount_sar) : ""}</td>
                </tr>
              )) : <tr><td colSpan={5} className="empty">{t("No lines")}</td></tr>}
            </tbody>
            <tfoot>
              <tr>
                <td colSpan={3}>{balanced ? t("Total") : t("Total, not balanced")}</td>
                <td className="n">{fmt(totalDebit)}</td>
                <td className="n" style={balanced ? undefined : { color: "var(--danger-text)" }}>{fmt(totalCredit)}</td>
              </tr>
            </tfoot>
          </table>
        </div>
      </DCard>
    </DPage>
  );
}
