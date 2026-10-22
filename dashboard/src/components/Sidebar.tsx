/**
 * Global navigation.
 *
 * The results view group (DB-003~DB-010) is listed but disabled. Showing it is a
 * lead ruling (J-2): the A8 decision — one application, two view groups — only
 * becomes visible as structure if the second group is present as a planned absence.
 * Hiding it would make this look like a finished app that happens to have six screens.
 *
 * Disabled here means actually disabled: `aria-disabled`, removed from the tab order,
 * no href, and a reason in the accessible name. A link that looks dead but still
 * navigates, or one that is only visually greyed, fails both keyboard and screen
 * reader users.
 */
import Image from "next/image";
import Link from "next/link";

import { SPRINT_ROUTES } from "@/components/sprint/routes";

/** C1 — the observability group. Routes are owned by index.json `views`/`static_views`. */
const OBSERVABILITY = [
  { href: "/", label: "개요" },
  { href: "/ingestion", label: "수집 현황" },
  { href: "/rejections", label: "계약 위반" },
  { href: "/coverage", label: "필드 충족률" },
  { href: "/kpi", label: "KPI" },
  { href: "/quality", label: "데이터 품질" },
  { href: "/freeze", label: "봉인 상태" },
  { href: "/triggers", label: "모니터링 트리거" },
];

/**
 * Later cycles — src/decision/ publishes these. No route files exist for them; an
 * empty directory would read as "implemented".
 */
const RESULTS = [
  "이탈 예측",
  "코호트",
  "Uplift",
  "CLV",
  "세그먼트",
  "최적화",
  "실험",
  "타깃 임계",
];

export function Sidebar() {
  return (
    <nav
      aria-label="화면 이동"
      className="w-(--container-dashboard-sidebar) shrink-0 border-r border-border bg-surface px-base py-lg"
    >
      {/* Service logo slot. Swap public/brand/service-logo.svg for the Figma export —
          no code change needed. `unoptimized` because next/image refuses SVG otherwise. */}
      <Link href="/" className="mb-lg block" aria-label="서비스 홈">
        <Image
          src="/brand/service-logo.svg"
          alt="서비스 로고"
          width={32}
          height={32}
          unoptimized
          priority
          className="h-8 w-auto"
        />
      </Link>

      <p className="text-label-md text-text">관측 화면군</p>
      <p className="mt-xs text-caption text-text-muted">측정 계층 게시물</p>
      <ul className="mt-md flex flex-col gap-xs">
        {OBSERVABILITY.map((item) => (
          <li key={item.href}>
            <Link
              href={item.href}
              className="obs-transition block rounded-md px-sm py-sm text-body-sm text-text hover:bg-surface-selected"
            >
              {item.label}
            </Link>
          </li>
        ))}
      </ul>

      {/* Sprint result screens (issue 147). Read results/sprint-v0/latest/, or the
          mock fixtures when AIROI_SPRINT_SOURCE=mock — every screen then says so. */}
      <p className="mt-xl text-label-md text-text">스프린트 결과</p>
      <p className="mt-xs text-caption text-text-muted">sprint-v0 · 봉인 전 잠정 결과</p>
      <ul className="mt-md flex flex-col gap-xs">
        {SPRINT_ROUTES.map((item) => (
          <li key={item.href}>
            <Link
              href={item.href}
              className="obs-transition block rounded-md px-sm py-sm text-body-sm text-text hover:bg-surface-selected"
            >
              {item.label}
            </Link>
          </li>
        ))}
      </ul>

      <p className="mt-xl text-label-md text-text">결과 화면군</p>
      <p className="mt-xs text-caption text-text-muted">이후 사이클 · 모델 산출물 필요</p>
      <ul className="mt-md flex flex-col gap-xs">
        {RESULTS.map((label) => (
          <li key={label}>
            <span
              aria-disabled="true"
              // No tabIndex and no href: the item is announced and skipped, not focusable.
              className="block cursor-not-allowed rounded-md px-sm py-sm text-body-sm text-(--ds-components-button-disabled-text-color)"
              aria-label={`${label} — 이후 사이클입니다. 모델 산출물이 없어 열 수 없습니다.`}
            >
              {label}
            </span>
          </li>
        ))}
      </ul>
      <p className="mt-md text-caption text-text-secondary">
        결과 화면군은 이후 사이클입니다. 모델 산출물이 없어 열 수 없습니다.
      </p>
    </nav>
  );
}
