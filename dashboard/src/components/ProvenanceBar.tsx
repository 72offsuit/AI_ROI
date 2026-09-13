/**
 * "What am I looking at" (DB-013).
 *
 * Everything here is copied from the artifact envelope. `generated_by` in particular
 * is recorded by the generator at run time rather than written into a design document,
 * so printing it verbatim cannot be a claim the pipeline never made.
 *
 * A null field is printed as an em dash plus its reason code — never as an empty
 * string or a placeholder, since "we did not capture the commit" and "there is no
 * simulator" are different facts and `null_reason` distinguishes them.
 */
import type { Envelope } from "@/lib/artifacts/types";
import { FixtureBadge } from "./StateChip";

/** Set AIROI_FIXTURE_MODE=1 when pointing the reader at staged sample artifacts. */
function isFixtureMode(): boolean {
  const flag = process.env.AIROI_FIXTURE_MODE;
  return typeof flag === "string" && flag.trim().length > 0 && flag.trim() !== "0";
}

export function ProvenanceBar({ envelope }: { envelope: Envelope }) {
  const p = envelope.provenance;
  const reasonFor = (key: string): string => {
    const reasons = p.null_reason;
    if (reasons === undefined) return "사유 미표기";
    const code = reasons[key];
    return code === undefined ? "사유 미표기" : code;
  };
  const orDash = (value: string | null | undefined, key: string) =>
    typeof value === "string" && value.length > 0 ? value : `— (${reasonFor(key)})`;

  return (
    <section
      aria-label="게시물 신원"
      className="flex flex-col gap-xs rounded-lg border border-border bg-surface-muted px-base py-md"
    >
      <div className="flex flex-wrap items-center gap-sm">
        <span className="text-label-md text-text">게시물 신원</span>
        {isFixtureMode() ? <FixtureBadge /> : null}
      </div>
      <dl className="grid grid-cols-1 gap-xs text-caption text-text-secondary md:grid-cols-2">
        <Row label="계약" value={envelope.contract_version} />
        <Row label="실행 ID" value={envelope.run_id} />
        <Row label="게시 시각" value={`${envelope.generated_at} (${envelope.timezone})`} />
        <Row label="이벤트 스키마" value={p.schema_version} />
        <Row label="저장소 커밋" value={orDash(p.repo_commit, "repo_commit")} />
        <Row label="데이터 버전" value={orDash(p.data_version, "data_version")} />
        <Row label="시뮬레이터 커밋" value={orDash(p.simulator_commit, "simulator_commit")} />
        <Row label="원천" value={p.source_root} />
        <Row label="생성 명령" value={p.generated_by} />
      </dl>
    </section>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex gap-xs">
      <dt className="shrink-0">{label}</dt>
      <dd className="min-w-0 break-all text-text">{value}</dd>
    </div>
  );
}

/**
 * Manual refresh only (DB-011). No polling: a screen that reloads on its own can show
 * a half-published run, and every route is already `force-dynamic` so a normal reload
 * re-reads the files.
 */
export function RefreshLink({ route }: { route: string }) {
  return (
    <a
      // A plain link to this page's own route. Every route is force-dynamic, so
      // following it re-reads the artifacts from disk — no client JS, and it works
      // with keyboard, middle-click and "open in new tab" like any other link.
      href={route}
      className="obs-transition inline-flex h-control-md items-center rounded-md border border-border px-base text-label-md text-primary hover:bg-surface-selected"
    >
      새로고침
    </a>
  );
}

/** Cycle notice — states that today's mostly-uncomputable screen is the correct state. */
export function CycleNotice() {
  return (
    <section
      aria-label="현재 사이클 기대 상태"
      className="rounded-lg bg-(--obs-unconnected-surface) px-base py-md text-(--obs-unconnected-ink)"
    >
      <p className="text-label-md">C1 관측 사이클 — 계산 불가 지표가 많은 것이 정상입니다.</p>
      <p className="mt-xs text-body-sm">
        커머스 이벤트 0건(Ecommerce #28 미착수) · 시뮬레이터 미구현 · 결과 화면군은 이후
        사이클입니다.
      </p>
    </section>
  );
}
