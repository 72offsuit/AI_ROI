/**
 * Sprint result overview (issue 147): run identity, stage states, the `sealed:false`
 * warning, and which of the eight files exist.
 *
 * Stage order is the file's order (DG-11 — no sorting that pushes failures down).
 */
import type { Metadata } from "next";
import Link from "next/link";

import { loadRunMeta, loadSprint, SPRINT_DIR, sprintSource } from "@/lib/artifacts/sprint";
import type { SprintFileName } from "@/lib/artifacts/sprint-types";
import { fmtInt, fmtSeconds } from "@/lib/format/sprint";
import { StateChip } from "@/components/StateChip";
import { Section, SprintGate, SprintHeader, TableWrap, TD, TDR, TH, THR } from "@/components/sprint/SprintFrame";
import { SPRINT_ROUTES } from "@/components/sprint/routes";
import { Txt, Val } from "@/components/sprint/Value";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "스프린트 결과 · 개요" };

function stageChip(status: string) {
  if (status === "ok") return <StateChip state="ok" label="완료" />;
  if (status === "not_run") return <StateChip state="not_run" label="미실행" />;
  if (status === "failed") return <StateChip state="violation" label="실패" />;
  return <StateChip state="violation" label={`알 수 없는 상태 · ${status}`} />;
}

export default async function SprintOverviewPage() {
  const source = sprintSource();
  const meta = await loadRunMeta();
  const header = meta.kind === "ok" ? meta.artifact : null;

  const files: SprintFileName[] = [
    "run_meta",
    "churn_eval",
    "clv_eval",
    "uplift_eval",
    "segments",
    "strategy_comparison",
    "ab_test",
    "realism_report",
  ];
  const fileStates = await Promise.all(files.map(async (f) => ({ file: f, result: await loadSprint(f) })));
  const routeOf = (file: SprintFileName) => SPRINT_ROUTES.find((r) => r.files.includes(file));

  return (
    <div className="flex flex-col gap-lg">
      <SprintHeader
        title="스프린트 결과 · 개요"
        description="sprint-v0 파이프라인(시뮬레이터 → 측정 → 예측·Uplift·최적화 → 실험)의 실행 메타와 단계 상태입니다."
        source={source}
        header={header}
      />

      {header !== null && !header.sealed ? (
        <section className="rounded-lg border border-(--obs-provisional-border) bg-(--obs-gap-surface) px-base py-md" role="note">
          <StateChip state="provisional" label="봉인 전 결과 · sealed:false" />
          <p className="mt-xs text-body-md text-text">
            이 결과는 봉인(GATE)되지 않았습니다. 파라미터·라벨 정의가 확정되기 전의 잠정 값이며, 최종 성능 주장에 쓰지 않습니다.
          </p>
        </section>
      ) : null}

      {meta.kind !== "ok" ? (
        <SprintGate result={meta} />
      ) : (
        <>
          <Section title="실행 메타">
            <dl className="grid grid-cols-1 gap-x-base gap-y-sm md:grid-cols-3">
              {[
                ["run_id", <code key="r" className="font-mono text-body-md break-all">{meta.artifact.run_id}</code>],
                ["seed", <Val key="s" text={fmtInt(meta.artifact.seed)} />],
                ["고객 수 N", <Val key="n" text={fmtInt(meta.artifact.N)} />],
                ["profile", <Txt key="p" text={meta.artifact.profile} />],
                ["simulator_version", <Txt key="v" text={meta.artifact.simulator_version} />],
                ["생성 시각", <Txt key="g" className="text-body-md" text={meta.artifact.generated_at} />],
              ].map(([k, v]) => (
                <div key={k as string} className="flex flex-col gap-xs">
                  <dt className="text-caption text-text-secondary">{k}</dt>
                  <dd className="text-headline-sm text-text">{v}</dd>
                </div>
              ))}
            </dl>
          </Section>

          <Section title="단계 상태" note="파일에 적힌 순서 그대로입니다. 미실행·실패 단계는 사유를 함께 표시합니다.">
            {(meta.artifact.stages ?? []).length === 0 ? (
              <StateChip state="violation" label="stages 가 비어 있습니다" />
            ) : (
              <TableWrap label="단계 상태 표">
                <thead>
                  <tr>
                    <th className={TH}>단계</th>
                    <th className={TH}>상태</th>
                    <th className={TH}>사유</th>
                    <th className={THR}>소요</th>
                  </tr>
                </thead>
                <tbody>
                  {(meta.artifact.stages ?? []).map((s) => (
                    <tr key={s.name}>
                      <td className={TD}>
                        <code className="font-mono">{s.name}</code>
                      </td>
                      <td className={TD}>{stageChip(s.status)}</td>
                      <td className={TD}>
                        {s.status === "ok" ? (
                          <span className="text-text-secondary">—</span>
                        ) : (
                          <Txt text={s.reason} />
                        )}
                      </td>
                      <td className={TDR}>
                        <Val text={fmtSeconds(s.seconds)} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </TableWrap>
            )}
          </Section>
        </>
      )}

      <Section
        title="결과 파일"
        note={
          source === "mock"
            ? "목업 모드 — dashboard/fixtures/sprint-v0/ 의 손으로 만든 파일입니다. 데이터 근거는 목업이 없어 미생성입니다."
            : `${SPRINT_DIR}/ 를 읽습니다. 데이터 근거(realism_report.json)는 공개판 docs/research/realism_public.json 의 사본입니다 — 없으면 미생성.`
        }
      >
        <TableWrap label="결과 파일 상태 표">
          <thead>
            <tr>
              <th className={TH}>파일</th>
              <th className={TH}>상태</th>
              <th className={TH}>화면</th>
            </tr>
          </thead>
          <tbody>
            {fileStates.map(({ file, result }) => {
              const route = routeOf(file);
              return (
                <tr key={file}>
                  <td className={TD}>
                    <code className="font-mono">{file}.json</code>
                  </td>
                  <td className={TD}>
                    {result.kind === "ok" ? (
                      <StateChip state="ok" label="있음" />
                    ) : result.kind === "missing" ? (
                      <StateChip state="not_run" label="미생성" />
                    ) : result.kind === "run-id-mismatch" ? (
                      <StateChip state="violation" label="run_id 불일치" />
                    ) : (
                      <StateChip state="violation" label="형식 위반" />
                    )}
                  </td>
                  <td className={TD}>
                    {route === undefined ? null : (
                      <Link href={route.href} className="text-primary underline">
                        {route.label}
                      </Link>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </TableWrap>
      </Section>
    </div>
  );
}
