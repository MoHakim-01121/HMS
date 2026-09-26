import { RvBack } from "./record-view.jsx";

// Back link for list/form pages. Renders the same link as detail pages'
// RvBack so every "Back" in the app looks alike; the wrapper only adds the
// gap before the page header. RvBack already hides itself inside a FormModal.
export default function PageBack({ href = "/", label = "Back" }) {
  return (
    <div className="hms-page-back">
      <RvBack href={href} label={label} />
    </div>
  );
}
