import { useForm } from "@inertiajs/react";
import { withStandaloneModal } from "../../components/shadcn/form-modal.jsx";
import FormHeader from "../../components/shadcn/form-header.jsx";
import FormPanel from "../../components/shadcn/form-panel.jsx";
import FormSection from "../../components/shadcn/form-section.jsx";
import FormField from "../../components/shadcn/form-field.jsx";
import FormActions from "../../components/shadcn/form-actions.jsx";
import PageBack from "../../components/shadcn/page-back.jsx";
import { Textarea } from "../../components/shadcn/ui/textarea.jsx";
import { useI18n } from "../../utils/i18n.jsx";
import { Alert } from "../../components/shadcn/ui/alert.jsx";
import Page from "../../components/shadcn/page.jsx";

// Void a finance document (an invoice or a credit note) with a required
// reason. When the server lists blockers, the form explains them instead.
function VoidFormBody({ kicker, title, number, sub, action, cancel, blockers = [], error, reason = "" }) {
  const { t } = useI18n();
  const form = useForm({ reason });
  const blocked = blockers.length > 0;

  const submit = (e) => {
    e.preventDefault();
    form.post(action);
  };

  return (
    <Page size="form">
      <PageBack href={cancel} label={t("Back")} />
      <FormHeader kicker={t(kicker)} title={`${t(title)} ${number}`} sub={t(sub)} />
      {error && <Alert variant="destructive" className="mb-3">{t(error)}</Alert>}
      <form method="post" onSubmit={submit}>
        <FormPanel>
          <FormSection label={t("Details")}>
            {blocked ? (
              <ul className="m-0 pl-[18px] text-[13px] leading-[1.6] text-yellow">
                {blockers.map((b) => <li key={b}>{t(b)}</li>)}
              </ul>
            ) : (
              <FormField label={t("Reason")} name="reason" required hint={t("Kept on the record and printed on the document.")}>
                <Textarea id="reason" rows={3} autoFocus value={form.data.reason} onChange={(e) => form.setData("reason", e.target.value)} />
              </FormField>
            )}
          </FormSection>
          <FormActions
            cancelHref={cancel}
            submitLabel={blocked ? null : form.processing ? t("Saving…") : t("Void")}
            processing={form.processing || !form.data.reason.trim()}
          />
        </FormPanel>
      </form>
    </Page>
  );
}

export default withStandaloneModal(VoidFormBody, (props) => props.cancel);
