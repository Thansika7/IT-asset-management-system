import React from "react";

/**
 * Reusable pagination component.
 *
 * Props:
 *   page        – current page (1-indexed)
 *   totalPages  – total number of pages
 *   onPageChange – (newPage) => void
 *   pageSize    – items per page (optional, for display)
 *   total       – total item count (optional, for display)
 */
export default function Pagination({ page, totalPages, onPageChange, pageSize, total }) {
  if (!totalPages || totalPages <= 1) return null;

  const pages = buildPageList(page, totalPages);

  return (
    <div className="pagination-bar">
      {total !== undefined && pageSize !== undefined && (
        <span className="pagination-info">
          Showing {Math.min((page - 1) * pageSize + 1, total)}–{Math.min(page * pageSize, total)} of {total}
        </span>
      )}

      <div className="pagination-controls">
        {/* Previous */}
        <button
          className="pagination-btn"
          onClick={() => onPageChange(page - 1)}
          disabled={page === 1}
          aria-label="Previous page"
        >
          ‹
        </button>

        {/* Page numbers */}
        {pages.map((p, i) =>
          p === "..." ? (
            <span key={`ellipsis-${i}`} className="pagination-ellipsis">…</span>
          ) : (
            <button
              key={p}
              className={`pagination-btn ${p === page ? "pagination-btn--active" : ""}`}
              onClick={() => onPageChange(p)}
              aria-current={p === page ? "page" : undefined}
            >
              {p}
            </button>
          )
        )}

        {/* Next */}
        <button
          className="pagination-btn"
          onClick={() => onPageChange(page + 1)}
          disabled={page === totalPages}
          aria-label="Next page"
        >
          ›
        </button>
      </div>
    </div>
  );
}

/** Build page list with ellipsis for large page counts */
function buildPageList(current, total) {
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1);

  const pages = [];
  pages.push(1);

  if (current > 3) pages.push("...");

  const start = Math.max(2, current - 1);
  const end   = Math.min(total - 1, current + 1);
  for (let i = start; i <= end; i++) pages.push(i);

  if (current < total - 2) pages.push("...");

  pages.push(total);
  return pages;
}
