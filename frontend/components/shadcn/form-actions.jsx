import { Button } from "./ui/button.jsx";

// shadcn Button-based rebuild of ../form/FormActions.jsx — same props.
export default function FormActions({ cancelHref, submitLabel, processing }) {
  return (
    <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
      <Button asChild variant="ghost">
        <a href={cancelHref}>Cancel</a>
      </Button>
      <Button type="submit" disabled={processing}>
        {submitLabel}
      </Button>
    </div>
  );
}
