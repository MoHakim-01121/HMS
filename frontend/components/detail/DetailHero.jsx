import KebabMenu from "./KebabMenu.jsx";

// Hero gradasi oranye halaman detail: pill status kiri-atas, menu titik-tiga
// kanan-atas, kicker kapital kecil, nomor dokumen besar, satu baris info sekunder.
export default function DetailHero({ kicker, title, sub, pill, menuItems }) {
  return (
    <div className="dv-hero">
      <div className="dv-hero-top">
        <span className={"dv-pill" + (pill && pill.tone ? ` ${pill.tone}` : "")}>{pill ? pill.label : ""}</span>
        <KebabMenu items={menuItems} />
      </div>
      <div className="dv-hero-kicker">{kicker}</div>
      <div className="dv-hero-title">{title}</div>
      {sub ? <div className="dv-hero-sub">{sub}</div> : null}
    </div>
  );
}
