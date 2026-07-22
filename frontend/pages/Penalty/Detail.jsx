import { router } from "@inertiajs/react";
import { useConfirm } from "../../components/ui/ConfirmDialog.jsx";
import DetailHero from "../../components/detail/DetailHero.jsx";
import FloatCard from "../../components/detail/FloatCard.jsx";
import Section from "../../components/detail/Section.jsx";
import ItemRow from "../../components/detail/ItemRow.jsx";
import FooterSummary from "../../components/detail/FooterSummary.jsx";

const fmt = (n) => Math.round(n || 0).toLocaleString("en-US");

export default function Detail({ penalty: p }) {
  const [confirm, confirmDialog] = useConfirm();
  const del = () => confirm({ title: "Delete penalty", message: `Delete penalty document ${p.penalty_number}?`, onConfirm: () => router.post(`/penalty/${p.id}/delete/`) });
  const paySub = [p.payment_date, p.payment_note].filter(Boolean);
  return (
    <div className="page dv-page">
      <a href={`/cl/${p.cl.id}/`} className="page-back">
        <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 12H5m7-7l-7 7 7 7" />
        </svg>
        Back to CL
      </a>

      <DetailHero
        kicker="Cancellation Penalty"
        title={p.penalty_number}
        sub={<>CL : <a href={`/cl/${p.cl.id}/`}>{p.cl.confirmation_number}</a></>}
        pill={p.is_paid ? { label: "Paid", tone: "green" } : { label: "Unpaid", tone: "yellow" }}
        menuItems={[
          { label: "PDF", href: `/penalty/${p.id}/pdf/`, target: "_blank" },
          { label: "Edit", href: `/penalty/${p.id}/edit/` },
          { label: "Delete", onClick: del, danger: true },
        ]}
      />

      <FloatCard
        right={
          <div className={"dv-amtbox" + (p.is_paid ? " paid" : "")}>
            <div className="dv-l">{p.is_paid ? "Paid" : "Penalty Due"}</div>
            <div className="dv-amtbox-num">{fmt(p.penalty_amount)}</div>
            <div className="dv-amtbox-cur">{p.penalty_currency}</div>
          </div>
        }
      >
        <div className="dv-l">Guest</div>
        <div className="dv-float-name">{p.cl.guest_name}</div>
        <div className="dv-item-sub">{p.cl.confirmation_number}</div>
      </FloatCard>

      <div className="dv-body">
      <Section label="Details">
        {p.cancellation_date ? <ItemRow small name={p.cancellation_date} sub="Cancellation Date" /> : null}
        {p.exchange_rate !== 1 ? <ItemRow small name={p.exchange_rate} sub="Exchange Rate" /> : null}
        {p.reason ? <div className="dv-item-sub" style={{ marginTop: 6 }}>{p.reason}</div> : null}
      </Section>

      {p.is_paid ? (
        <Section label="Payment">
          <ItemRow
            small
            name={p.payment_method || "Paid"}
            sub={paySub.length ? paySub.map((l, i) => <span key={i}>{i > 0 ? <br /> : null}{l}</span>) : null}
            amount={fmt(p.penalty_amount)}
            amountColor="green"
          />
        </Section>
      ) : null}

      {p.note ? (
        <Section label="Notes">
          <div className="dv-item-sub" style={{ marginTop: 6, whiteSpace: "pre-wrap" }}>{p.note}</div>
        </Section>
      ) : null}

      <FooterSummary
        right={
          <>
            <div className="dv-l">Total Penalty</div>
            <div className="dv-foot-total">{fmt(p.penalty_amount)}<span className="cur"> {p.penalty_currency}</span></div>
          </>
        }
      />
      </div>
      {confirmDialog}
    </div>
  );
}
