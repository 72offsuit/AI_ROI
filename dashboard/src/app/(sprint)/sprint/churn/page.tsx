/**
 * Churn prediction (issue 147): baseline vs proposed metric table, per-metric bars with
 * CV error bars, SHAP top features — and the CLV evaluation underneath, since clv_eval
 * has no screen of its own in the sprint.
 *
 * Model order is the file's order. Nothing is re-ranked by score.
 */
import type { Metadata } from "next";

import { loadSprint, sprintSource } from "@/lib/artifacts/sprint";
import { fmtDec, fmtInt, fmtKrw, fmtMeanStd, fmtPct, meanStd } from "@/lib/format/sprint";
import { BarChart, KindLegend } from "@/components/sprint/charts";
import { Section, SprintGate, SprintHeader, TableWrap, TD, TDR, TH, THR } from "@/components/sprint/SprintFrame";
import { KindTag, Txt, Val } from "@/components/sprint/Value";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "스프린트 결과 · 이탈 예측" };

const METRICS: { key: string; label: string; domain?: [number, number] }[] = [
  { key: "roc_auc", label: "ROC-AUC", domain: [0, 1] },
  { key: "pr_auc", label: "PR-AUC", domain: [0, 1] },
  { key: "f1", label: "F1", domain: [0, 1] },
  { key: "lift_at_10", label: "Lift@10%" },
];

export default async function ChurnPage() {
  const source = sprintSource();
  const churn = await loadSprint("churn_eval");
  const clv = await loadSprint("clv_eval");

  return (
    <div className="flex flex-col gap-lg">
      <SprintHeader
        title="이탈 예측"
        description="이탈 분류 모델의 교차검증·시간 홀드아웃 성능을 기준선과 비교하고, 영향이 큰 Feature 를 보여줍니다."
        source={source}
        header={churn.kind === "ok" ? churn.artifact : null}
      />

      {churn.kind !== "ok" ? (
        <SprintGate result={churn} />
      ) : (
        <>
          <Section title="평가 조건">
            <dl className="grid grid-cols-1 gap-sm md:grid-cols-3">
              <div>
                <dt className="text-caption text-text-secondary">라벨 정의</dt>
                <dd className="text-body-md text-text">
                  <Txt text={churn.artifact.label_def} />
                </dd>
              </div>
              <div>
                <dt className="text-caption text-text-secondary">표본 수</dt>
                <dd className="text-headline-sm text-text">
                  <Val text={fmtInt(churn.artifact.n)} />
                </dd>
              </div>
              <div>
                <dt className="text-caption text-text-secondary">이탈(양성) 비율</dt>
                <dd className="text-headline-sm text-text">
                  <Val text={fmtPct(churn.artifact.pos_rate)} />
                </dd>
              </div>
            </dl>
          </Section>

          <Section title="모델 비교 — 교차검증 (평균 ± 표준편차)">
            <TableWrap label="이탈 모델 교차검증 지표 표">
              <thead>
                <tr>
                  <th className={TH}>모델</th>
                  <th className={TH}>구분</th>
                  {METRICS.map((m) => (
                    <th key={m.key} className={THR}>
                      {m.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {(churn.artifact.models ?? []).map((model) => (
                  <tr key={model.name}>
                    <td className={TD}>{model.name}</td>
                    <td className={TD}>
                      <KindTag kind={model.kind} />
                    </td>
                    {METRICS.map((m) => (
                      <td key={m.key} className={TDR}>
                        <Val text={fmtMeanStd(model.cv?.[m.key])} />
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </TableWrap>

            <KindLegend />
            <div className="flex flex-col gap-base">
              {METRICS.map((m) => (
                <figure key={m.key} className="flex flex-col gap-xs">
                  <figcaption className="text-label-md text-text">{m.label}</figcaption>
                  <BarChart
                    ariaLabel={`${m.label} 모델별 막대, 오차막대는 교차검증 표준편차`}
                    domain={m.domain}
                    rows={(churn.artifact.models ?? []).map((model) => {
                      const v = meanStd(model.cv?.[m.key]);
                      return {
                        key: model.name,
                        label: model.name,
                        emphasis: model.kind === "proposed",
                        value: v.mean,
                        err: v.std,
                        display: fmtMeanStd(model.cv?.[m.key]),
                      };
                    })}
                  />
                </figure>
              ))}
            </div>
          </Section>

          <Section
            title="모델 비교 — 시간 홀드아웃"
            note="학습 기간 이후 구간으로 평가한 값입니다. 값이 없으면 계산 불가로 표시합니다(개요의 단계 상태에서 사유 확인)."
          >
            <TableWrap label="이탈 모델 시간 홀드아웃 지표 표">
              <thead>
                <tr>
                  <th className={TH}>모델</th>
                  <th className={TH}>구분</th>
                  {METRICS.map((m) => (
                    <th key={m.key} className={THR}>
                      {m.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {(churn.artifact.models ?? []).map((model) => (
                  <tr key={model.name}>
                    <td className={TD}>{model.name}</td>
                    <td className={TD}>
                      <KindTag kind={model.kind} />
                    </td>
                    {METRICS.map((m) => (
                      <td key={m.key} className={TDR}>
                        <Val text={fmtMeanStd(model.temporal_holdout?.[m.key])} />
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </TableWrap>
          </Section>

          <Section
            title="영향 상위 Feature"
            note={
              typeof churn.artifact.importance_method === "string"
                ? `산출 방법 · ${churn.artifact.importance_method}`
                : "산출 방법 미표기"
            }
          >
            {(churn.artifact.shap_top ?? []).length === 0 ? (
              <Val text={null} />
            ) : (
              <BarChart
                ariaLabel="Feature 별 평균 절대 SHAP 값"
                rows={(churn.artifact.shap_top ?? []).map((f) => ({
                  key: f.feature,
                  label: f.feature,
                  emphasis: true,
                  value: typeof f.mean_abs === "number" ? f.mean_abs : null,
                  display: fmtDec(f.mean_abs),
                }))}
              />
            )}
          </Section>
        </>
      )}

      <Section title="CLV 예측" note="고객 생애가치 회귀 모델 비교. 예측 기간은 파일의 horizon_days 입니다.">
        {clv.kind !== "ok" ? (
          <SprintGate result={clv} />
        ) : (
          <>
            <p className="text-body-sm text-text">
              예측 기간 · <Val text={fmtInt(clv.artifact.horizon_days)} />일
            </p>
            <TableWrap label="CLV 모델 지표 표">
              <thead>
                <tr>
                  <th className={TH}>모델</th>
                  <th className={TH}>구분</th>
                  <th className={THR}>MAE</th>
                  <th className={THR}>RMSE</th>
                  <th className={THR}>Spearman ρ</th>
                  <th className={THR}>상위 20% 적중</th>
                </tr>
              </thead>
              <tbody>
                {(clv.artifact.models ?? []).map((m) => (
                  <tr key={m.name}>
                    <td className={TD}>{m.name}</td>
                    <td className={TD}>
                      <KindTag kind={m.kind} />
                    </td>
                    <td className={TDR}>
                      <Val text={fmtKrw(m.mae)} />
                    </td>
                    <td className={TDR}>
                      <Val text={fmtKrw(m.rmse)} />
                    </td>
                    <td className={TDR}>
                      <Val text={fmtDec(m.spearman)} />
                    </td>
                    <td className={TDR}>
                      <Val text={fmtPct(m.top20_hit)} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </TableWrap>
          </>
        )}
      </Section>
    </div>
  );
}
