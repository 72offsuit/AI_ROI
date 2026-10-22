/**
 * Shared chrome of the sprint-v0 result screens: title, source badge, run identity and
 * the `sealed:false` warning, plus the gate shown when a file cannot be drawn.
 *
 * ★ The source badge is decided by how the loader was configured, not by anything in
 *   the file — a mock file that forgot to say so is still badged.
 */
import Link from "next/link";

import type { SprintLoad, SprintSource } from "@/lib/artifacts/sprint";
import type { SprintFileName, SprintHeader as Header } from "@/lib/artifacts/sprint-types";
import { MockBadge, StateChip } from "@/components/StateChip";

export function SprintHeader({
  title,
  description,
  source,
  header,
}: {
  title: string;
  description: string;
  source: SprintSource;
  header: Header | null;
}) {
  return (
    <header className="flex flex-col gap-sm">
      <div className="flex flex-wrap items-center justify-between gap-sm">
        <h1 className="text-headline-lg text-text">{title}</h1>
        <Link href="?" className="text-label-md text-primary underline" prefetch={false}>
          새로고침
        </Link>
      </div>
      <p className="text-body-sm text-text-secondary">{description}</p>
      <div className="flex flex-wrap items-center gap-xs">
        {source === "mock" ? (
          <MockBadge />
        ) : (
          <span className="text-caption text-text-secondary">출처 · results/sprint-v0/latest/</span>
        )}
        {header === null ? null : (
          <>
            {header.sealed ? (
              <StateChip state="ok" label="봉인됨 · sealed:true" />
            ) : (
              <StateChip state="provisional" label="봉인 전 · sealed:false — 잠정 결과" />
            )}
            <span className="text-caption text-text-secondary">
              {header.sprint} · run_id <code className="font-mono">{header.run_id}</code> · 생성{" "}
              {header.generated_at}
            </span>
          </>
        )}
      </div>
    </header>
  );
}

/** The one rendering of "this file cannot be drawn", with its reason always visible. */
export function SprintGate({ result }: { result: Exclude<SprintLoad<SprintFileName>, { kind: "ok" }> }) {
  return (
    <section className="rounded-lg border border-border bg-surface px-base py-md" aria-live="polite">
      {result.kind === "missing" ? (
        <>
          <StateChip state="not_run" label="미생성 · 파일이 아직 없습니다" />
          <p className="mt-sm text-body-sm text-text">
            <code className="font-mono">{result.path}</code> 가 없습니다. 값을 0 으로 채우지 않고 이 화면을 비워 둡니다.
          </p>
          <p className="mt-xs text-caption text-text-secondary">
            스프린트 파이프라인이 이 파일을 쓰면 새로고침으로 표시됩니다. 목업으로 화면만 확인하려면{" "}
            <code className="font-mono">npm run dev:sprint-mock</code> 으로 실행하십시오 (목업 배지가 붙습니다).
          </p>
        </>
      ) : result.kind === "run-id-mismatch" ? (
        <>
          <StateChip state="violation" label="run_id 불일치 · 두 실행의 값을 섞지 않습니다" />
          <p className="mt-sm text-body-sm text-text">
            <code className="font-mono">{result.path}</code> 의 run_id{" "}
            <code className="font-mono">{result.found}</code> 가 run_meta.json 의{" "}
            <code className="font-mono">{result.expected}</code> 와 다릅니다. 게시가 진행 중이거나 파일이 섞였습니다.
          </p>
        </>
      ) : (
        <>
          <StateChip state="violation" label="읽을 수 없음 · 형식 위반" />
          <p className="mt-sm text-body-sm text-text">
            <code className="font-mono">{result.path}</code> — {result.message}
          </p>
        </>
      )}
    </section>
  );
}

export function Section({
  title,
  note,
  children,
}: {
  title: string;
  note?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="flex flex-col gap-sm rounded-lg border border-border bg-surface p-base">
      <h2 className="text-headline-sm text-text">{title}</h2>
      {note === undefined ? null : <p className="text-caption text-text-secondary">{note}</p>}
      {children}
    </section>
  );
}

/** Horizontal scroll for wide tables, never hidden columns (dashboard/AGENTS.md §8). */
export function TableWrap({ children, label }: { children: React.ReactNode; label: string }) {
  return (
    <div className="overflow-x-auto" role="region" aria-label={label} tabIndex={0}>
      <table className="w-full min-w-max border-collapse text-body-sm">{children}</table>
    </div>
  );
}

export const TH = "border-b border-border px-sm py-sm text-left text-label-md text-text-secondary";
export const THR = "border-b border-border px-sm py-sm text-right text-label-md text-text-secondary";
export const TD = "border-b border-border px-sm py-sm text-left align-top text-text";
export const TDR = "border-b border-border px-sm py-sm text-right align-top";
