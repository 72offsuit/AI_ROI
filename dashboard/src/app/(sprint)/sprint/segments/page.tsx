/**
 * Segments (issue 147): per-segment size, share, average churn probability, average
 * CATE and average CLV, in the file's order (S1, S2, …) — never re-sorted by size.
 */
import type { Metadata } from "next";

import { loadSprint, sprintSource } from "@/lib/artifacts/sprint";
import { fmtInt, fmtKrw, fmtPct, fmtSigned, isNum } from "@/lib/format/sprint";
import { BarChart } from "@/components/sprint/charts";
import { Section, SprintGate, SprintHeader, TableWrap, TD, TDR, TH, THR } from "@/components/sprint/SprintFrame";
import { Txt, Val } from "@/components/sprint/Value";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "스프린트 결과 · 세그먼트" };

export default async function SegmentsPage() {
  const source = sprintSource();
  const seg = await loadSprint("segments");
  const rows = seg.kind === "ok" ? (seg.artifact.segments ?? []) : [];

  return (
    <div className="flex flex-col gap-lg">
      <SprintHeader
        title="세그먼트"
        description="이탈 확률·처치 반응(CATE)·생애가치(CLV)로 나눈 고객 세그먼트입니다. 순서는 파일의 세그먼트 ID 순서입니다."
        source={source}
        header={seg.kind === "ok" ? seg.artifact : null}
      />

      {seg.kind !== "ok" ? (
        <SprintGate result={seg} />
      ) : (
        <>
          <Section title="세그먼트 표">
            <TableWrap label="세그먼트 표">
              <thead>
                <tr>
                  <th className={TH}>ID</th>
                  <th className={TH}>이름</th>
                  <th className={THR}>고객 수</th>
                  <th className={THR}>비중</th>
                  <th className={THR}>평균 이탈 확률</th>
                  <th className={THR}>평균 CATE</th>
                  <th className={THR}>평균 CLV</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((s) => (
                  <tr key={s.id}>
                    <td className={TD}>
                      <code className="font-mono">{s.id}</code>
                    </td>
                    <td className={TD}>
                      <Txt text={s.name} />
                    </td>
                    <td className={TDR}>
                      <Val text={fmtInt(s.n)} />
                    </td>
                    <td className={TDR}>
                      <Val text={fmtPct(s.share)} />
                    </td>
                    <td className={TDR}>
                      <Val text={fmtPct(s.avg_churn_p)} />
                    </td>
                    <td className={TDR}>
                      <Val text={fmtSigned(s.avg_cate)} />
                    </td>
                    <td className={TDR}>
                      <Val text={fmtKrw(s.avg_clv)} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </TableWrap>
          </Section>

          <div className="flex flex-col gap-base">
            <Section title="비중">
              <BarChart
                ariaLabel="세그먼트별 고객 비중"
                rows={rows.map((s) => ({
                  key: s.id,
                  label: `${s.id} ${typeof s.name === "string" ? s.name : ""}`.trim(),
                  emphasis: true,
                  value: isNum(s.share) ? s.share : null,
                  display: fmtPct(s.share),
                }))}
              />
            </Section>
            <Section title="평균 CATE" note="음수는 처치하면 오히려 이탈이 늘어나는 세그먼트입니다.">
              <BarChart
                ariaLabel="세그먼트별 평균 CATE"
                rows={rows.map((s) => ({
                  key: s.id,
                  label: `${s.id} ${typeof s.name === "string" ? s.name : ""}`.trim(),
                  emphasis: true,
                  value: isNum(s.avg_cate) ? s.avg_cate : null,
                  display: fmtSigned(s.avg_cate),
                }))}
              />
            </Section>
          </div>
        </>
      )}
    </div>
  );
}
