import Table from "./table.jsx";
import EmptyState from "./empty-state.jsx";
import Pagination from "./pagination.jsx";

// Shared list-page body: the `.hms-list-card` shell that renders the rows
// table (plus pagination) or, when there is nothing to show, the EmptyState.
// Consolidates the repeated `hms-list-card { rows ? <Table/><Pagination/> :
// <EmptyState/> }` block across every list page.
//
//   columns / rows / rowKey / onRowClick   forwarded to <Table>
//   empty                                  { icon, title, sub, filteredTitle, filteredSub }
//                                          `filteredTitle/sub` replace title/sub when
//                                          `hasFilter` is truthy (active q/status/etc.)
//   hasFilter                              true → use the "no results" empty copy
//   pagination / page+numPages+total       pagination shapes, see <Pagination>
//   unit / onPage                          handled by <Pagination>
export default function ListCard({
  columns, rows = [], rowKey, onRowClick,
  empty, hasFilter = false,
  pagination, page, numPages, total,
  unit = "results", onPage,
}) {
  if (!rows || !rows.length) {
    const { icon, title, sub, filteredTitle, filteredSub } = empty || {};
    const showFiltered = hasFilter && filteredTitle;
    return (
      <div className="hms-list-card">
        <EmptyState
          iconName={icon}
          title={showFiltered ? filteredTitle : title}
          sub={showFiltered ? filteredSub : sub}
        />
      </div>
    );
  }

  return (
    <div className="hms-list-card">
      <Table columns={columns} rows={rows} rowKey={rowKey} onRowClick={onRowClick} />
      <Pagination
        pagination={pagination}
        page={page}
        numPages={numPages}
        total={total}
        unit={unit}
        onPage={onPage}
      />
    </div>
  );
}