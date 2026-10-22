/**
 * Data grounding (issue 147): generated vs real-data reference values with the
 * research team's verdict per metric, and a link to the grounding write-up.
 *
 * ★ Source: `docs/research/realism_report.json` is outside what the dashboard may read
 *   (DG-1, DB-014), so the screen reads its copy in `results/sprint-v0/latest/`. The
 *   verdict is the file's own field; the screen does not compare the two numbers.
 * ★ Metric order is the file's order — "deviates" rows are not pushed down (DG-11).
 */
import type { Metadata } from "next";

import { loadSprint, SPRINT_DIR, sprintSource } from "@/lib/artifacts/sprint";
import { fmtAuto } from "@/lib/format/sprint";
import { StateChip } from "@/components/StateChip";
import { Section, SprintGate, SprintHeader, TableWrap, TD, TDR, TH, THR } from "@/components/sprint/SprintFrame";
import { Txt, Val } from "@/components/sprint/Value";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "스프린트 결과 · 데이터 근거" };

const GROUNDING_DOC =
  "https://github.com/72offsuit/AI_ROI/blob/main/docs/research/data_grounding.md";
const REPORT_DOC =
  "https://github.com/72offsuit/AI_ROI/blob/main/docs/research/realism_report.json";

// realism_check.py writes its own verdict (pass · borderline · fail · no_data) and the same
// verdict in the dashboard vocabulary (dashboard_verdict). The raw word is shown so that
// borderline and fail — both "deviates" — stay distinguishable.
function verdictChip(raw: string | null | undefined, dashboard: string | null | undefined) {
  if (raw === "pass") return <StateChip state="ok" label="통과 · pass" />;
  if (raw === "borderline") return <StateChip state="gap" label="경계 · borderline" />;
  if (raw === "fail") return <StateChip state="gap" label="실패 · fail" />;
  if (raw === "no_data") return <StateChip state="planned" label="데이터 없음 · no_data" />;
  const v = dashboard ?? raw;
  if (v === "consistent") return <StateChip state="ok" label="일치 · consistent" />;
  if (v === "deviates") return <StateChip state="gap" label="차이 있음 · deviates" />;
  if (v === "no_reference") return <StateChip state="planned" label="참조값 없음 · no_reference" />;
  return <StateChip state="violation" label={`판정 미표기 · ${String(v)}`} />;
}

// Lists a value as the file gives it: a number, a [lo, hi] band, or named sub-values.
// Nested records (e.g. `uncapped`) are not flattened — only scalar entries are shown.
function ValueList({ value }: { value: unknown }) {
  if (Array.isArray(value) && value.length === 2) {
    const [lo, hi] = value.map((x) => fmtAuto(x));
    return lo === null || hi === null ? <Val text={null} /> : <Val text={`${lo} ~ ${hi}`} />;
  }
  if (value !== null && typeof value === "object" && !Array.isArray(value)) {
    const entries = Object.entries(value as Record<string, unknown>).filter(
      ([, v]) => typeof v === "number" || typeof v === "boolean" || (Array.isArray(v) && v.length === 2),
    );
    if (entries.length === 0) return <Val text={null} />;
    return (
      <>
        {entries.map(([k, v]) => (
          <span key={k} className="block whitespace-nowrap">
            <span className="text-text-secondary">{k}</span>{" "}
            {typeof v === "boolean" ? <Val text={String(v)} /> : <ValueList value={v} />}
          </span>
        ))}
      </>
    );
  }
  return <Val text={fmtAuto(value)} />;
}

function safeUrl(url: string | null | undefined): string | null {
  return typeof url === "string" && /^https?:\/\//.test(url) ? url : null;
}

export default async function GroundingPage() {
  const source = sprintSource();
  const report = await loadSprint("realism_report");
  const metrics = report.kind === "ok" ? (report.artifact.metrics ?? []) : [];

  return (
    <div className="flex flex-col gap-lg">
      <SprintHeader
        title="데이터 근거"
        description="시뮬레이터가 생성한 데이터의 주요 분포를 공개 실데이터의 값과 나란히 놓고, 리서치 판정을 그대로 표시합니다."
        source={source}
        header={null}
      />

      <Section title="근거 문서">
        <ul className="flex flex-col gap-xs text-body-sm">
          <li>
            <a href={GROUNDING_DOC} className="text-primary underline" target="_blank" rel="noreferrer">
              docs/research/data_grounding.md
            </a>{" "}
            <span className="text-text-secondary">— 참조 데이터셋 선정 근거와 지표 정의</span>
          </li>
          <li>
            <a href={REPORT_DOC} className="text-primary underline" target="_blank" rel="noreferrer">
              docs/research/realism_report.json
            </a>{" "}
            <span className="text-text-secondary">
              — 원본. 대시보드는 사본 <code className="font-mono">{SPRINT_DIR}/realism_report.json</code> 을 읽습니다
            </span>
          </li>
        </ul>
      </Section>

      {report.kind !== "ok" ? (
        <SprintGate result={report} />
      ) : (
        <Section title="생성 vs 실데이터" note="판정은 리서치 파일의 verdict 그대로입니다. 참조값이 없는 지표는 0 이 아니라 계산 불가로 표시합니다.">
          {metrics.length === 0 ? (
            <StateChip state="violation" label="metrics 가 비어 있습니다" />
          ) : (
            <TableWrap label="생성 데이터와 실데이터 비교표">
              <thead>
                <tr>
                  <th className={TH}>지표</th>
                  <th className={TH}>단위</th>
                  <th className={THR}>생성 (시뮬레이터)</th>
                  <th className={THR}>실데이터 (값 · 통과 범위)</th>
                  <th className={TH}>참조 데이터셋</th>
                  <th className={TH}>판정</th>
                </tr>
              </thead>
              <tbody>
                {metrics.map((m) => {
                  const url = safeUrl(m.reference?.source_url);
                  return (
                    <tr key={m.id ?? m.name}>
                      <td className={TD}>
                        {typeof m.id === "string" ? <code className="font-mono">{m.id}</code> : null} {m.name}
                      </td>
                      <td className={TD}>
                        <Txt text={m.unit} />
                      </td>
                      <td className={TDR}>
                        <ValueList value={m.synthetic} />
                      </td>
                      <td className={TDR}>
                        {m.reference?.value !== undefined && m.reference?.value !== null ? (
                          <ValueList value={m.reference.value} />
                        ) : null}
                        {m.reference?.band !== undefined && m.reference?.band !== null ? (
                          <span className="block">
                            <span className="text-text-secondary">범위</span> <ValueList value={m.reference.band} />
                          </span>
                        ) : null}
                        {(m.reference?.value === undefined || m.reference?.value === null) &&
                        (m.reference?.band === undefined || m.reference?.band === null) ? (
                          <Val text={null} />
                        ) : null}
                      </td>
                      <td className={TD}>
                        {m.reference === null || m.reference === undefined ? (
                          <span className="text-(--obs-absent-ink)">참조 없음</span>
                        ) : url === null ? (
                          <Txt text={m.reference.dataset} />
                        ) : (
                          <a href={url} className="text-primary underline" target="_blank" rel="noreferrer">
                            <Txt text={m.reference.dataset} />
                          </a>
                        )}
                      </td>
                      <td className={TD}>{verdictChip(m.verdict, m.dashboard_verdict)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </TableWrap>
          )}
        </Section>
      )}
    </div>
  );
}
