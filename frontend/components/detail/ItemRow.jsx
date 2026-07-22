// Baris item seragam: nama tebal kiri (+ link kecil opsional), sub abu-abu
// multi-baris di bawahnya, angka tebal rata kanan (+ sub angka opsional).

// Link kecil "CL"/"Proof": teks oranye + ikon buka-tab, tanpa background/border.
export function DvLink({ href, newTab, children }) {
  return (
    <a className="dv-link" href={href} target={newTab ? "_blank" : undefined} rel={newTab ? "noreferrer" : undefined}>
      {children}
      <svg viewBox="0 0 24 24"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" /><path d="M15 3h6v6" /><path d="M10 14L21 3" /></svg>
    </a>
  );
}

export default function ItemRow({ name, link, sub, amount, amountSub, amountColor, small }) {
  return (
    <div className="dv-item">
      <div className="dv-item-main">
        <div className={"dv-item-name" + (small ? " sm" : "")}>{name}{link}</div>
        {sub ? <div className="dv-item-sub">{sub}</div> : null}
      </div>
      {amount != null ? (
        <div className="dv-item-amt" style={amountColor ? { color: `var(--${amountColor})` } : undefined}>
          {amount}
          {amountSub}
        </div>
      ) : null}
    </div>
  );
}
