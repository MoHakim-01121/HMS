import { Component } from "react";
import { usePage } from "@inertiajs/react";
import { Button } from "@/components/shadcn/ui/button";
import { useI18n } from "../../utils/i18n.jsx";

function CrashNotice() {
  const { t } = useI18n();
  return (
    <div role="alert" className="flex min-h-[60vh] flex-col items-center justify-center gap-3 px-4 text-center">
      <h1 className="text-lg font-semibold text-foreground">{t("This page could not be displayed")}</h1>
      <p className="max-w-md text-sm text-muted-foreground">{t("Your saved data is safe. Reload the page, or contact the admin if this keeps happening.")}</p>
      <Button onClick={() => window.location.reload()}>{t("Reload page")}</Button>
    </div>
  );
}

// React unmounts everything on a render error; without this the screen goes
// blank. React still logs the error to the console.
export class ErrorBoundary extends Component {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    return this.state.failed ? <CrashNotice /> : this.props.children;
  }
}

// Inside the shell: the menu stays usable, and going to another page clears it.
export function PageErrorBoundary({ children }) {
  const { url } = usePage();
  return <ErrorBoundary key={url.split("?")[0]}>{children}</ErrorBoundary>;
}
