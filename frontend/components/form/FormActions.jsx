export default function FormActions({ cancelHref, submitLabel, processing }) {
  return (
    <div className="form-actions">
      <a href={cancelHref} className="btn btn-ghost">Batal</a>
      <button type="submit" className="btn btn-primary" disabled={processing}>
        <svg width="13" height="13" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" /></svg>
        {submitLabel}
      </button>
    </div>
  );
}
