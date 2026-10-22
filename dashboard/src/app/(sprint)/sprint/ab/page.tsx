/**
 * A/B test (issue 147): sample-ratio-mismatch check, per-arm rate and difference vs
 * control with 95% CI, raw and Holm-adjusted p-values, and the power summary.
 *
 * The only verdict shown (SRM ok) is the file's own `srm.ok` field — the screen does not
 * run or re-judge a test.
 */
import type { Metadata } from "next";

import { loadSprint, sprintSource } from "@/lib/artifacts/sprint";
import { fmtAuto, fmtDec, fmtInt, fmtInterval, fmtP, fmtPct, fmtPp, isNum } from "@/lib/format/sprint";
import { StateChip } from "@/components/StateChip";
import { IntervalChart } from "@/components/sprint/charts";
import { Section, SprintGate, SprintHeader, TableWrap, TD, TDR, TH, THR } from "@/components/sprint/SprintFrame";
import { Val } from "@/components/sprint/Value";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "스프린트 결과 · A/B" };

export default async function AbPage() {
  const source = sprintSource();
  const ab = await loadSprint("ab_test");

  if (ab.kind !== "ok") {
    return (
      <div className="flex flex-col gap-lg">
        <SprintHeader title="A/B 실험" description="처치군 비교 실험" source={source} header={null} />
        <SprintGate result={ab} />
      </div>
    );
  }
  const a = ab.artifact;
  const arms = a.arms ?? [];
  const treated = arms.filter((r) => isNum(r.diff_vs_control) || Array.isArray(r.ci95));
  const power = Object.entries(a.power ?? {});

  return (
    <div className="flex flex-col gap-lg">
      <SprintHeader
        title="A/B 실험"
        description="무작위 배정 실험의 표본 비율 점검(SRM), 처치군별 이탈률과 대조군 대비 차이, 다중비교 보정(Holm) p-value 입니다."
        source={source}
        header={a}
      />

      <Section title="표본 비율 점검 (SRM)" note="배정 비율이 설계와 다르면 이후 모든 비교를 믿을 수 없습니다.">
        <div className="flex flex-wrap items-center gap-base">
          {a.srm?.ok === true ? (
            <StateChip state="ok" label="SRM 없음 · 배정 비율 정상" />
          ) : a.srm?.ok === false ? (
            <StateChip state="violation" label="SRM 감지 · 배정 비율 이상" />
          ) : (
            <StateChip state="not_run" label="SRM 판정 미표기" />
          )}
          <span className="text-body-md text-text">
            χ² <Val text={fmtDec(a.srm?.chi2, 2)} /> · p <Val text={fmtP(a.srm?.p)} />
          </span>
        </div>
      </Section>

      <Section title="처치군별 결과">
        <TableWrap label="A/B 처치군 표">
          <thead>
            <tr>
              <th className={TH}>처치군</th>
              <th className={THR}>n</th>
              <th className={THR}>이탈률</th>
              <th className={THR}>대조군 대비 (%p)</th>
              <th className={THR}>95% CI</th>
              <th className={THR}>p (원)</th>
              <th className={THR}>p (Holm)</th>
            </tr>
          </thead>
          <tbody>
            {arms.map((r) => (
              <tr key={r.arm}>
                <td className={TD}>{r.arm}</td>
                <td className={TDR}>
                  <Val text={fmtInt(r.n)} />
                </td>
                <td className={TDR}>
                  <Val text={fmtPct(r.rate)} />
                </td>
                {r.diff_vs_control === null && r.ci95 === null && r.p_raw === null ? (
                  <td className={TDR} colSpan={4}>
                    <span className="text-text-secondary">대조군 (비교 기준)</span>
                  </td>
                ) : (
                  <>
                    <td className={TDR}>
                      <Val text={fmtPp(r.diff_vs_control)} />
                    </td>
                    <td className={TDR}>
                      <Val text={fmtInterval(r.ci95, (x) => fmtPp(x))} />
                    </td>
                    <td className={TDR}>
                      <Val text={fmtP(r.p_raw)} />
                    </td>
                    <td className={TDR}>
                      <Val text={fmtP(r.p_holm)} />
                    </td>
                  </>
                )}
              </tr>
            ))}
          </tbody>
        </TableWrap>

        {treated.length === 0 ? null : (
          <figure className="flex flex-col gap-xs">
            <figcaption className="text-label-md text-text">대조군 대비 이탈률 차이 (95% CI)</figcaption>
            <IntervalChart
              ariaLabel="처치군별 대조군 대비 이탈률 차이와 95% 신뢰구간"
              rows={treated.map((r) => {
                const d = fmtPp(r.diff_vs_control);
                const ci = fmtInterval(r.ci95, (x) => fmtPp(x));
                return {
                  key: r.arm,
                  label: r.arm,
                  value: isNum(r.diff_vs_control) ? r.diff_vs_control : null,
                  lo: Array.isArray(r.ci95) && isNum(r.ci95[0]) ? r.ci95[0] : null,
                  hi: Array.isArray(r.ci95) && isNum(r.ci95[1]) ? r.ci95[1] : null,
                  display: d === null ? null : `${d} ${ci === null ? "" : ci}`.trim(),
                };
              })}
            />
          </figure>
        )}
      </Section>

      <Section title="검정력" note="파일의 power 항목을 그대로 나열합니다.">
        {power.length === 0 ? (
          <Val text={null} />
        ) : (
          <dl className="flex flex-wrap gap-x-xl gap-y-sm">
            {power.map(([k, v]) => (
              <div key={k}>
                <dt className="text-caption text-text-secondary">
                  <code className="font-mono">{k}</code>
                </dt>
                <dd className="text-headline-sm text-text">
                  {typeof v === "string" ? v : typeof v === "boolean" ? String(v) : <Val text={fmtAuto(v)} />}
                </dd>
              </div>
            ))}
          </dl>
        )}
      </Section>
    </div>
  );
}
