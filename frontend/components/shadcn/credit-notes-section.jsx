import { Icon } from "../icons.jsx";
import { useI18n } from "../../utils/i18n.jsx";
import { fmt } from "../../utils/format.js";

// Credit notes of one invoice (hotel or service detail): number, date,
// reason, amount, PDF, and a void action for those allowed to reverse it.
// Voided notes stay listed, struck through, for the audit trail.
export default function CreditNotesSection({ creditNotes = [], canVoid, openForm }) {
  const { t } = useI18n();
  if (!creditNotes.length) return null;
  return (
    <section className="hms-cl-sec">
      <div className="hms-cl-sech">
        <h2>{t("Credit notes")}</h2>
        <span className="meta">{t("Reduce what this invoice bills")}</span>
      </div>
      <div className="hms-iv-grid cn">
        <div className="hms-iv-gh">
          <span>{t("Credit note")}</span><span>{t("Reason")}</span><span className="r">SAR</span><span />
        </div>
        {creditNotes.map((cn) => {
          const voided = cn.status === "voided";
          return (
            <div className="hms-iv-gr" key={cn.id} style={voided ? { opacity: 0.55 } : undefined}>
              <div className="c-id">
                <div className="top">
                  <a className="mono strong hms-iv-link" href={`/finance/credit-notes/${cn.id}/pdf/`} target="_blank" rel="noreferrer">{cn.number}</a>
                  {voided ? <span className="hms-dv-pill hms-iv-pill-sm tone-gray">{t("Void")}</span> : null}
                </div>
                <div className="sub tab">{cn.date}</div>
              </div>
              <div className="c-method">
                <span className="cn-reason">{voided && cn.voided_reason ? `${cn.reason} · ${t("voided")}: ${cn.voided_reason}` : cn.reason}</span>
                {cn.to_deposit_sar > 0 && !voided ? (
                  <span className="sub">{t("{n} SAR to client deposit", { n: fmt(cn.to_deposit_sar) })}</span>
                ) : null}
              </div>
              <span className="r tab strong" data-label="SAR">
                {voided ? <s>{fmt(cn.amount_sar)}</s> : `−${fmt(cn.amount_sar)}`}
              </span>
              <span className="r">
                {canVoid && !voided ? (
                  <button type="button" className="hms-iv-chip" onClick={() => openForm(`/finance/credit-notes/${cn.id}/void/`)}>
                    <Icon name="close" size={10} strokeWidth={2} aria-hidden="true" />
                    {t("Void")}
                  </button>
                ) : null}
              </span>
            </div>
          );
        })}
      </div>
    </section>
  );
}
