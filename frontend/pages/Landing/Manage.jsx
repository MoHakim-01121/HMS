import { router } from "@inertiajs/react";
import { Icon } from "../../components/icons.jsx";
import PageHeader from "../../components/shadcn/page-header.jsx";
import { DPage, DCard, DBtn } from "../../components/shadcn/detail-a.jsx";
import Table from "../../components/shadcn/table.jsx";
import EmptyState from "../../components/shadcn/empty-state.jsx";
import RowActions from "../../components/shadcn/row-actions.jsx";
import { useConfirm } from "../../components/shadcn/confirm-dialog.jsx";
import { useFormModal } from "../../components/shadcn/form-modal.jsx";
import { usePerms } from "../../utils/perms.js";
import { useI18n } from "../../utils/i18n.jsx";

export default function Manage({ team_members, pricelist }) {
  const { t } = useI18n();
  const perms = usePerms();
  const openForm = useFormModal();
  const [confirm, confirmDialog] = useConfirm();

  const members = team_members || [];
  const file = pricelist || null;

  const deleteMember = (m) => {
    confirm({
      title: t("Delete member"),
      message: t("Remove {name} from the team?", { name: m.name }),
      onConfirm: () => router.post(`/manage-landing/team/${m.id}/delete/`),
    });
  };

  const deletePricelist = (p) => {
    confirm({
      title: t("Delete pricelist"),
      message: t("Delete pricelist “{title}”?", { title: p.title }),
      onConfirm: () => router.post(`/manage-landing/pricelist/${p.id}/delete/`),
    });
  };

  return (
    <DPage>
      <PageHeader
        title={t("Manage Landing")}
        sub={t("Team members and the pricelist shown on the public page")}
        actions={<DBtn href="/?preview=1" target="_blank" rel="noreferrer">{t("Preview public page")}</DBtn>}
      />

      <DCard
        title={t("Our Team")}
        count={members.length}
        sub={t("Name, position and WhatsApp shown on the landing page")}
        actions={perms.can("landing", "create") && (
          <DBtn primary onClick={() => openForm("/manage-landing/team/new/")}>{t("+ New Member")}</DBtn>
        )}
      >
        {members.length ? (
          <Table
            columns={[
              {
                header: t("Photo"), mobile: "meta",
                render: (v) => (v.photo_url ? (
                  <img src={v.photo_url} alt={v.name} style={{ width: 30, height: 30, borderRadius: "50%", objectFit: "cover", display: "block" }} />
                ) : (
                  <Icon name="user" size={18} style={{ color: "var(--muted-foreground)" }} />
                )),
              },
              { header: t("Name"), mobile: "primary", render: (v) => v.name },
              { header: t("Position"), mobile: "secondary", render: (v) => v.position || "—" },
              { header: t("WhatsApp"), className: "col-muted col-nowrap", render: (v) => (v.wa ? <a href={`https://wa.me/${v.wa}`} target="_blank" rel="noreferrer">{v.wa}</a> : "—") },
              { header: t("Order"), className: "col-muted", mobile: "meta", render: (v) => v.order },
              {
                header: "", mobile: "actions",
                render: (v) => (
                  <RowActions actions={[
                    perms.can("landing", "edit") && { icon: "edit", label: t("Edit"), onClick: () => openForm(`/manage-landing/team/${v.id}/edit/`) },
                    perms.can("landing", "delete") && { icon: "trash", label: t("Delete"), variant: "red", onClick: () => deleteMember(v) },
                  ]} />
                ),
              },
            ]}
            rows={members}
            rowKey={(v) => v.id}
          />
        ) : (
          <EmptyState title="Belum ada anggota tim" sub="Gunakan + New Member di atas untuk menambahkan" />
        )}
      </DCard>

      <DCard
        title={t("Pricelist")}
        sub={t("Only one pricelist is active — a new upload replaces the old one")}
        actions={perms.can("landing", "create") && (
          <DBtn primary onClick={() => openForm("/manage-landing/pricelist/new/")}>
            {file ? t("+ Replace Pricelist") : t("+ Upload Pricelist")}
          </DBtn>
        )}
      >
        {file ? (
          <Table
            columns={[
              { header: t("Title"), mobile: "primary", render: (v) => v.title },
              {
                header: t("File"), mobile: "secondary",
                render: (v) => (v.file_url ? <a href={v.file_url} target="_blank" rel="noreferrer">{v.filename}</a> : "—"),
              },
              { header: t("Updated"), className: "col-muted col-nowrap", render: (v) => v.updated_at },
              {
                header: "", mobile: "actions",
                render: (v) => (
                  <RowActions actions={[
                    perms.can("landing", "edit") && { icon: "edit", label: t("Edit"), onClick: () => openForm(`/manage-landing/pricelist/${v.id}/edit/`) },
                    perms.can("landing", "delete") && { icon: "trash", label: t("Delete"), variant: "red", onClick: () => deletePricelist(v) },
                  ]} />
                ),
              },
            ]}
            rows={[file]}
            rowKey={(v) => v.id}
          />
        ) : (
          <EmptyState title="Belum ada pricelist" sub="Gunakan + Upload Pricelist di atas" />
        )}
      </DCard>

      {confirmDialog}
    </DPage>
  );
}
