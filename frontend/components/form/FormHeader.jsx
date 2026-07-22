export default function FormHeader({ kicker, title, sub }) {
  return (
    <div className="dv-form-header">
      <div className="dv-l">{kicker}</div>
      <div className="page-title" style={{ marginTop: 3 }}>{title}</div>
      {sub && <div className="page-sub">{sub}</div>}
    </div>
  );
}
