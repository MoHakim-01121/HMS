import FormField from "../../components/shadcn/form-field.jsx";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "../../components/shadcn/ui/select.jsx";
import { useI18n } from "../../utils/i18n.jsx";

// Whose records the account sees: every branch (head office) or one branch.
// The admin role always covers every branch.
export default function BranchField({ role, value, onChange, choices = [], error }) {
  const { t } = useI18n();
  const isAdmin = role === "admin";
  return (
    <FormField
      label={t("Branch")} name="branch" error={error}
      hint={isAdmin ? t("Administrators cover every branch.") : t("Branch staff see only their branch's records; head office works across all branches.")}
    >
      <Select name="branch" value={isAdmin ? "all" : value} onValueChange={onChange} disabled={isAdmin}>
        <SelectTrigger id="branch" className="w-full">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {choices.map((c) => (
            <SelectItem key={c.value} value={c.value}>{c.value === "all" ? t("All branches") : c.label}</SelectItem>
          ))}
        </SelectContent>
      </Select>
    </FormField>
  );
}
