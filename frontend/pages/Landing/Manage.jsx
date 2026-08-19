import { router } from "@inertiajs/react";
import { Icon } from "../../components/icons.jsx";
import Table from "../../components/shadcn/table.jsx";
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
      message: t("Hapus {name} dari tim?", { name: m.name }),
      onConfirm: () => router.post(`/manage-landing/team/${m.id}/delete/`),
    });
  };

  const deletePricelist = (p) => {
    confirm({
      title: t("Delete pricelist"),
      message: t("Hapus pricelist “{title}”?", { title: p.title }),
      onConfirm: () => router.post(`/manage-landing/pricelist/${p.id}/delete/`),
    });
  };

  return (
    <div className="page shadcn-root">
      <div className="page-header">
        <div>
          <div className="page-title">{t("Manage Landing")}</div>
          <div className="page-sub">{t("Tim anggota dan pricelist yang tampil di halaman publik")}</div>
        </div>
        <a href="/?preview=1" target="_blank" rel="noreferrer" className="btn btn-secondary">
          {t("Preview Halaman Publik")}
        </a>
      </div>

      <div className="card">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12, flexWrap: "wrap", gap: 8 }}>
          <div>
            <div className="page-title" style={{ fontSize: 15 }}>{t("Our Team")}</div>
            <div style={{ fontSize: 12, color: "var(--muted-foreground)", marginTop: 2 }}>{t("Nama, jabatan dan WhatsApp yang tampil di landing page")}</div>
          </div>
          {perms.can("landing", "create") && (
            <button type="button" className="btn btn-primary" onClick={() => openForm("/manage-landing/team/new/")}>
              {t("+ New Member")}
            </button>
          )}
        </div>

        {members.length ? (
          <Table
            columns={[
              {
                header: t("Photo"), className: "col-m-meta",
                render: (v) => (v.photo_url ? (
                  <img src={v.photo_url} alt={v.name} style={{ width: 30, height: 30, borderRadius: "50%", objectFit: "cover", display: "block" }} />
                ) : (
                  <Icon name="user" size={18} style={{ color: "var(--muted-foreground)" }} />
                )),
              },
              { header: t("Name"), className: "col-m-primary", render: (v) => v.name },
              { header: t("Position"), className: "col-m-secondary", render: (v) => v.position || "—" },
              { header: t("WhatsApp"), className: "col-muted col-nowrap", render: (v) => (v.wa ? <a href={`https://wa.me/${v.wa}`} target="_blank" rel="noreferrer">{v.wa}</a> : "—") },
              { header: t("Order"), className: "col-muted col-m-meta", render: (v) => v.order },
              {
                header: "", className: "col-m-actions",
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
          <div className="empty">
            <Icon name="users" size={36} strokeWidth={1.5} />
            <div className="empty-title">{t("Belum ada anggota tim")}</div>
            <div className="empty-sub">{t("Gunakan + New Member di atas untuk menambahkan")}</div>
          </div>
        )}
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12, flexWrap: "wrap", gap: 8 }}>
          <div>
            <div className="page-title" style={{ fontSize: 15 }}>{t("Pricelist")}</div>
            <div style={{ fontSize: 12, color: "var(--muted-foreground)", marginTop: 2 }}>{t("Hanya satu pricelist aktif — upload baru menggantikan yang lama")}</div>
          </div>
          {perms.can("landing", "create") && (
            <button type="button" className="btn btn-primary" onClick={() => openForm("/manage-landing/pricelist/new/")}>
              {file ? t("+ Replace Pricelist") : t("+ Upload Pricelist")}
            </button>
          )}
        </div>

        {file ? (
          <Table
            columns={[
              { header: t("Title"), className: "col-m-primary", render: (v) => v.title },
              {
                header: t("File"), className: "col-m-secondary",
                render: (v) => (v.file_url ? <a href={v.file_url} target="_blank" rel="noreferrer">{v.filename}</a> : "—"),
              },
              { header: t("Updated"), className: "col-muted col-nowrap", render: (v) => v.updated_at },
              {
                header: "", className: "col-m-actions",
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
          <div className="empty">
            <Icon name="download" size={36} strokeWidth={1.5} />
            <div className="empty-title">{t("Belum ada pricelist")}</div>
            <div className="empty-sub">{t("Gunakan + Upload Pricelist di atas")}</div>
          </div>
        )}
      </div>

      {confirmDialog}
    </div>
  );
}
