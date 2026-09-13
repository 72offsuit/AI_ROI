/**
 * Renders the non-success outcomes of a load, so that seven pages do not each
 * reimplement five branches and drift apart on the wording.
 *
 * Each branch states a different fact, and collapsing any two of them would lose
 * information the reader needs:
 *   missing           — nothing has been published yet
 *   contract-mismatch — published against a contract this build cannot read (R-6)
 *   run-id-mismatch   — two files from two different runs (never mix them)
 *   violation         — the publisher broke its own contract
 *
 * ★ None of these render partial data. Drawing "whatever parsed" next to a warning is
 *   how a wrong number reaches a screenshot.
 */
import type { IndexLoadResult, LoadResult } from "@/lib/artifacts/read";
import { StateChip } from "./StateChip";

type AnyFailure = Exclude<LoadResult<unknown> | IndexLoadResult, { kind: "ok" }>;

export function ArtifactGate({ result }: { result: AnyFailure }) {
  switch (result.kind) {
    case "missing":
      return <EmptyState resultsDir={result.resultsDir} />;
    case "contract-mismatch":
      return (
        <Refusal
          title="계약 버전 불일치"
          lines={[
            `이 화면이 읽을 수 있는 계약은 ${result.expected} 입니다.`,
            `게시물이 선언한 계약은 ${result.found} 입니다.`,
            "필드 이름이 같아도 의미가 다를 수 있으므로 값을 렌더링하지 않습니다.",
          ]}
        />
      );
    case "run-id-mismatch":
      return (
        <Refusal
          title="게시가 진행 중이거나 불일치"
          lines={[
            `index.json 의 run_id 는 ${result.indexRunId} 입니다.`,
            `${result.artifactName} 의 run_id 는 ${result.artifactRunId} 입니다.`,
            "서로 다른 실행의 값을 섞어 표시하지 않습니다. 게시가 끝난 뒤 새로고침하십시오.",
          ]}
        />
      );
    case "violation":
      return <Refusal title="계약 위반 — 렌더링을 중단했습니다" lines={[result.message]} />;
  }
}

function Refusal({ title, lines }: { title: string; lines: string[] }) {
  return (
    <section className="rounded-lg border border-border bg-surface px-base py-lg">
      <StateChip state="violation" label={title} />
      <ul className="mt-sm flex flex-col gap-xs text-body-sm text-text">
        {lines.map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>
      <p className="mt-sm text-caption text-text-secondary">
        0 으로 채워진 값을 화면에 올리느니 화면이 비는 편이 낫습니다.
      </p>
    </section>
  );
}

/**
 * No artifacts at all.
 *
 * DB-013 requires telling the reader how to produce results; AGENTS.md forbids
 * writing commands that do not exist. Both hold at once only if the guidance names
 * what is needed without presenting a runnable command line — the publish entry point
 * is created by M-06 and, as of 2026-09-11, cannot be executed.
 *
 * ponytail: the "게시 명령은 아직 없습니다" sentence is accurate only until M-06 ships
 * `python3 -m src.measurement.publish`; replace it with the real command once that
 * module exists and has been run, not before.
 */
function EmptyState({ resultsDir }: { resultsDir: string }) {
  return (
    <section className="rounded-lg border border-border bg-surface px-base py-lg">
      <StateChip state="unconnected" label="게시물이 없습니다" />
      <p className="mt-sm text-body-sm text-text">
        측정 계층이 아직 산출물을 게시하지 않았습니다. 게시가 필요합니다.
      </p>
      <p className="mt-xs text-body-sm text-text">
        게시 명령은 W5-A 에서 신설됩니다 — 2026-09-11 현재 실행할 수 없습니다.
      </p>
      <p className="mt-sm text-caption text-text-secondary">
        읽는 위치: <code>{resultsDir}</code> · 환경변수 <code>AIROI_RESULTS_DIR</code> 로 바꿉니다.
      </p>
    </section>
  );
}
