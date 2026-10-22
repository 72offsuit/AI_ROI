/**
 * Uplift (issue 147): arm sizes, ATE with 95% CI per treatment, Qini/AUUC/uplift@k per
 * model, Qini curves. Arm and model order is the file's order.
 */
import type { Metadata } from "next";

import { loadSprint, sprintSource } from "@/lib/artifacts/sprint";
import { fmtDec, fmtInt, fmtInterval, fmtSigned, isNum } from "@/lib/format/sprint";
import { CurveChart, IntervalChart } from "@/components/sprint/charts";
import { Section, SprintGate, SprintHeader, TableWrap, TD, TDR, TH, THR } from "@/components/sprint/SprintFrame";
import { KindTag, Val } from "@/components/sprint/Value";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "스프린트 결과 · Uplift" };

export default async function UpliftPage() {
  const source = sprintSource();
  const up = await loadSprint("uplift_eval");

  if (up.kind !== "ok") {
    return (
      <div className="flex flex-col gap-lg">
        <SprintHeader title="Uplift" description="처치 효과(ATE)와 Uplift 모델 비교" source={source} header={null} />
        <SprintGate result={up} />
      </div>
    );
  }
  const a = up.artifact;
  const ate = Object.entries(a.ate ?? {});
  const models = a.models ?? [];
  const ks = Array.from(new Set(models.flatMap((m) => Object.keys(m.uplift_at_k ?? {}))));

  return (
    <div className="flex flex-col gap-lg">
      <SprintHeader
        title="Uplift"
        description="무작위 배정된 처치군별 평균 처치 효과(ATE)와, 누구에게 처치할지 고르는 Uplift 모델의 Qini·AUUC 를 비교합니다."
        source={source}
        header={a}
      />

      <Section title="배정 규모">
        <dl className="flex flex-wrap gap-x-xl gap-y-sm">
          <div>
            <dt className="text-caption text-text-secondary">전체 n</dt>
            <dd className="text-headline-sm text-text">
              <Val text={fmtInt(a.n)} />
            </dd>
          </div>
          {Object.entries(a.arms ?? {}).map(([arm, n]) => (
            <div key={arm}>
              <dt className="text-caption text-text-secondary">{arm}</dt>
              <dd className="text-headline-sm text-text">
                <Val text={fmtInt(n)} />
              </dd>
            </div>
          ))}
        </dl>
      </Section>

      <Section title="평균 처치 효과 (ATE · 95% 신뢰구간)" note="대조군(T0) 대비 차이입니다. 구간이 0 을 포함하면 효과가 있다고 말할 수 없습니다.">
        {ate.length === 0 ? (
          <Val text={null} />
        ) : (
          <>
            <IntervalChart
              ariaLabel="처치별 ATE 점추정과 95% 신뢰구간"
              rows={ate.map(([arm, e]) => {
                const lo = Array.isArray(e?.ci95) && isNum(e?.ci95?.[0]) ? (e?.ci95?.[0] as number) : null;
                const hi = Array.isArray(e?.ci95) && isNum(e?.ci95?.[1]) ? (e?.ci95?.[1] as number) : null;
                const v = fmtSigned(e?.value);
                const ci = fmtInterval(e?.ci95, (x) => fmtSigned(x));
                return {
                  key: arm,
                  label: arm,
                  value: isNum(e?.value) ? (e?.value as number) : null,
                  lo,
                  hi,
                  display: v === null ? null : `${v} ${ci === null ? "" : ci}`.trim(),
                };
              })}
            />
            <TableWrap label="ATE 표">
              <thead>
                <tr>
                  <th className={TH}>처치</th>
                  <th className={THR}>ATE</th>
                  <th className={THR}>95% CI</th>
                </tr>
              </thead>
              <tbody>
                {ate.map(([arm, e]) => (
                  <tr key={arm}>
                    <td className={TD}>{arm}</td>
                    <td className={TDR}>
                      <Val text={fmtSigned(e?.value)} />
                    </td>
                    <td className={TDR}>
                      <Val text={fmtInterval(e?.ci95, (x) => fmtSigned(x))} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </TableWrap>
          </>
        )}
      </Section>

      <Section title="모델 비교">
        <TableWrap label="Uplift 모델 지표 표">
          <thead>
            <tr>
              <th className={TH}>모델</th>
              <th className={TH}>구분</th>
              <th className={THR}>Qini</th>
              <th className={THR}>AUUC</th>
              {ks.map((k) => (
                <th key={k} className={THR}>
                  uplift@{k}%
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {models.map((m) => (
              <tr key={m.name}>
                <td className={TD}>{m.name}</td>
                <td className={TD}>
                  <KindTag kind={m.kind} />
                </td>
                <td className={TDR}>
                  <Val text={fmtDec(m.qini)} />
                </td>
                <td className={TDR}>
                  <Val text={fmtDec(m.auuc)} />
                </td>
                {ks.map((k) => (
                  <td key={k} className={TDR}>
                    <Val text={fmtDec(m.uplift_at_k?.[k])} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </TableWrap>
      </Section>

      <Section
        title="Qini 곡선"
        note="가로축은 모델 점수 상위부터 처치한 고객 비율, 세로축은 누적 증분 반응입니다. 곡선이 안내선 위로 높을수록 처치할 고객을 잘 고릅니다. 빠진 점은 잇지 않습니다."
      >
        {models.every((m) => (m.qini_curve ?? []).length === 0) ? (
          <Val text={null} />
        ) : (
          <CurveChart
            ariaLabel="모델별 Qini 곡선"
            xLabel="처치 대상 비율 (점수 상위부터)"
            yLabel="누적 증분 반응"
            series={models.map((m) => ({
              key: m.name,
              label: m.name,
              emphasis: m.kind === "proposed",
              points: m.qini_curve ?? [],
            }))}
          />
        )}
      </Section>
    </div>
  );
}
