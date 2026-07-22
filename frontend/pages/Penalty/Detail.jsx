import { router } from "@inertiajs/react";
import { useConfirm } from "../../components/shadcn/confirm-dialog.jsx";
import DetailHero from "../../components/shadcn/detail-hero.jsx";
import FloatCard from "../../components/shadcn/float-card.jsx";
import Section from "../../components/shadcn/section.jsx";
import ItemRow from "../../components/shadcn/item-row.jsx";
import FooterSummary from "../../components/shadcn/footer-summary.jsx";
import PageBack from "../../components/shadcn/page-back.jsx";

const fmt = (n) => Math.round(n || 0).toLocaleString("en-US");

export default function Detail({ penalty: p }) {
  const [confirm, confirmDialog] = useConfirm();
  const del = () => confirm({ title: "Delete penalty", message: `Delete penalty document ${p.penalty_number}?`, onConfirm: () => router.post(`/penalty/${p.id}/delete/`) });
  const paySub = [p.payment_date, p.payment_note].filter(Boolean);
  return (
    <div className="page dv-page">
      <PageBack href={`/cl/${p.cl.id}/`} label="Back to CL" />

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
