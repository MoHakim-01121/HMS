export default function FormActions({ cancelHref, submitLabel, processing }) {
  return (
    <div className="form-actions">
      <a href={cancelHref} className="btn btn-ghost">Cancel</a>
      <button type="submit" className="btn btn-primary" disabled={processing}>
        {submitLabel}
      </button>
    </div>
  );
}
