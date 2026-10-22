/**
 * Strategy & ROI (issue 147): S0~S5 comparison table, incremental profit vs S1 and ROI
 * bars. Strategy order is the file's order (S0 … S5); nothing is ranked by profit.
 */
import type { Metadata } from "next";

import { loadSprint, sprintSource } from "@/lib/artifacts/sprint";
import { fmtDec, fmtInt, fmtKrw, fmtPct, isNum } from "@/lib/format/sprint";
import { BarChart } from "@/components/sprint/charts";
import { Section, SprintGate, SprintHeader, TableWrap, TD, TDR, TH, THR } from "@/components/sprint/SprintFrame";
import { Txt, Val } from "@/components/sprint/Value";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "스프린트 결과 · 전략·ROI" };

export default async function StrategyPage() {
  const source = sprintSource();
  const st = await loadSprint("strategy_comparison");
  const rows = st.kind === "ok" ? (st.artifact.strategies ?? []) : [];
  const label = (s: (typeof rows)[number]) => `${s.id} ${typeof s.name === "string" ? s.name : ""}`.trim();
  // 증분이익의 계산 근거(DG-13). 실측 기여이익이 없으면 roi.py 가 매출 기준 대체 계산에 이 플래그를 붙인다.
  const revenueFallback = (s: (typeof rows)[number]) => (s.flags ?? []).includes("PROFIT_FALLBACK_REVENUE_BASED");
  const anyFallback = rows.some(revenueFallback);

  return (
    <div className="flex flex-col gap-lg">
      <SprintHeader
        title="전략·ROI"
        description="같은 기간·같은 고객에 대해 처치 전략 S0~S5 를 비교합니다. 증분이익은 S1(Rule 기준선 — 28~90일 미구매 · 구매 2회 이상 고객에게 윈백 쿠폰 T3) 대비입니다."
        source={source}
        header={st.kind === "ok" ? st.artifact : null}
      />

      {st.kind !== "ok" ? (
        <SprintGate result={st} />
      ) : (
        <>
          <Section title="비교 조건">
            <dl className="flex flex-wrap gap-x-xl gap-y-sm">
              <div>
                <dt className="text-caption text-text-secondary">평가 기간</dt>
                <dd className="text-headline-sm text-text">
                  <Txt text={st.artifact.window?.start} /> ~ <Txt text={st.artifact.window?.end} />
                </dd>
              </div>
              <div>
                <dt className="text-caption text-text-secondary">예산</dt>
                <dd className="text-headline-sm text-text">
                  <Val text={fmtKrw(st.artifact.budget_krw)} />
                </dd>
              </div>
            </dl>
          </Section>

          <Section title="전략 비교표" note="매출은 순매출(할인 후, 배송비 제외), 공헌이익은 원가·마케팅 비용 차감 후 값입니다 (DR-101).">
            <TableWrap label="전략 비교표">
              <thead>
                <tr>
                  <th className={TH}>전략</th>
                  <th className={THR}>대상 고객</th>
                  <th className={TH}>처치 구성</th>
                  <th className={THR}>매출</th>
                  <th className={THR}>마케팅 비용</th>
                  <th className={THR}>공헌이익</th>
                  <th className={THR}>이탈률</th>
                  <th className={THR}>증분이익 (vs S1)</th>
                  <th className={THR}>ROI</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((s) => {
                  const mix = Object.entries(s.treatment_mix ?? {});
                  return (
                    <tr key={s.id}>
                      <td className={TD}>
                        <code className="font-mono">{s.id}</code> <Txt text={s.name} />
                      </td>
                      <td className={TDR}>
                        <Val text={fmtInt(s.n_targeted)} />
                      </td>
                      <td className={TD}>
                        {mix.length === 0 ? (
                          <span className="text-text-secondary">처치 없음</span>
                        ) : (
                          mix.map(([t, n]) => (
                            <span key={t} className="block whitespace-nowrap">
                              {t} <Val text={fmtInt(n)} />
                            </span>
                          ))
                        )}
                      </td>
                      <td className={TDR}>
                        <Val text={fmtKrw(s.revenue)} />
                      </td>
                      <td className={TDR}>
                        <Val text={fmtKrw(s.marketing_cost)} />
                      </td>
                      <td className={TDR}>
                        <Val text={fmtKrw(s.contribution_profit)} />
                      </td>
                      <td className={TDR}>
                        <Val text={fmtPct(s.churn_rate)} />
                      </td>
                      <td className={TDR}>
                        <Val text={fmtKrw(s.incremental_profit_vs_S1, true)} />
                        {revenueFallback(s) ? (
                          <span className="block whitespace-nowrap text-text-secondary">매출 기준 대체 · COGS 미차감</span>
                        ) : null}
                      </td>
                      <td className={TDR}>
                        <Val text={fmtDec(s.roi, 2)} />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </TableWrap>
          </Section>

          <div className="flex flex-col gap-base">
            <Section
              title="증분이익 (vs S1)"
              note={
                anyFallback
                  ? "0 선 왼쪽은 S1 보다 손해입니다. ⚠ 실측 공헌이익이 없어 Δ(매출 − 마케팅 비용) 대체 계산입니다 — 원가(COGS)를 빼지 않아 과대평가될 수 있습니다 (이슈 #169)."
                  : "0 선 왼쪽은 S1 보다 손해입니다."
              }
            >
              <BarChart
                ariaLabel="전략별 S1 대비 증분이익"
                rows={rows.map((s) => ({
                  key: s.id,
                  label: label(s),
                  emphasis: true,
                  value: isNum(s.incremental_profit_vs_S1) ? s.incremental_profit_vs_S1 : null,
                  display: fmtKrw(s.incremental_profit_vs_S1, true),
                }))}
              />
            </Section>
            <Section title="ROI" note="파일에 ROI 값이 없는 전략(예: 마케팅 비용이 0 이라 분모가 없는 경우)은 0 이 아니라 계산 불가로 표시합니다.">
              <BarChart
                ariaLabel="전략별 ROI"
                rows={rows.map((s) => ({
                  key: s.id,
                  label: label(s),
                  emphasis: true,
                  value: isNum(s.roi) ? s.roi : null,
                  display: fmtDec(s.roi, 2),
                }))}
              />
            </Section>
          </div>
        </>
      )}
    </div>
  );
}
