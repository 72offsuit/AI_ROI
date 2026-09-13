/**
 * The table primitive behind the event-type matrix, the field list, the metric list,
 * the quality checks and the lock items.
 *
 * Rules that are easy to break and cost the most:
 *   - Zero rows and missing rows stay in the table (V-0). The reader came to find the
 *     gaps; a table that hides them is worse than no table.
 *   - Default order is the fixed canonical order, never count-descending: descending
 *     order pushes every zero to the bottom, which hides them without ever calling it
 *     hiding. /coverage is the single exception (fill rate ascending, gaps on top).
 *   - Columns are never dropped on narrow screens. The table area scrolls horizontally
 *     on its own; DESIGN.md forbids hiding important columns.
 *   - Row height 44px, text left, numbers right with tabular figures.
 */
import type { ReactNode } from "react";

export interface Column<Row> {
  key: string;
  header: string;
  align?: "left" | "right";
  render: (row: Row) => ReactNode;
}

export function CoverageTable<Row>({
  caption,
  columns,
  rows,
  rowKey,
}: {
  caption: string;
  columns: Column<Row>[];
  rows: Row[];
  rowKey: (row: Row) => string;
}) {
  return (
    // Only this wrapper scrolls, so the surrounding page never shifts sideways.
    <div className="w-full overflow-x-auto">
      <table className="w-full min-w-[48rem] border-collapse text-body-sm">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr className="border-b border-border">
            {columns.map((column) => (
              <th
                key={column.key}
                scope="col"
                className={`px-sm py-sm text-label-md text-text ${
                  column.align === "right" ? "text-right" : "text-left"
                }`}
              >
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={rowKey(row)} className="border-b border-border align-top">
              {columns.map((column) => (
                <td
                  key={column.key}
                  className={`min-h-control-md px-sm py-md ${
                    column.align === "right" ? "text-right" : "text-left"
                  }`}
                >
                  {column.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
