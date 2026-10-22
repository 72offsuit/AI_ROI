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

function verdictChip(verdict: string | null | undefined) {
  if (verdict === "consistent") return <StateChip state="ok" label="일치 · consistent" />;
  if (verdict === "deviates") return <StateChip state="gap" label="차이 있음 · deviates" />;
  if (verdict === "no_reference") return <StateChip state="planned" label="참조값 없음 · no_reference" />;
  return <StateChip state="violation" label={`판정 미표기 · ${String(verdict)}`} />;
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
                  <th className={THR}>실데이터</th>
                  <th className={TH}>참조 데이터셋</th>
                  <th className={TH}>판정</th>
                </tr>
              </thead>
              <tbody>
                {metrics.map((m) => {
                  const url = safeUrl(m.reference?.source_url);
                  return (
                    <tr key={m.name}>
                      <td className={TD}>{m.name}</td>
                      <td className={TD}>
                        <Txt text={m.unit} />
                      </td>
                      <td className={TDR}>
                        <Val text={fmtAuto(m.synthetic)} />
                      </td>
                      <td className={TDR}>
                        <Val text={fmtAuto(m.reference?.value)} />
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
                      <td className={TD}>{verdictChip(m.verdict)}</td>
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
