/**
 * Uplift (issue 147): arm sizes, ATE with 95% CI per treatment, Qini/AUUC/uplift@k per
 * model, Qini curves. Arm and model order is the file's order.
 *
 * The ATE is a difference in the file's `primary_outcome` (#299) — the note names it from the
 * file and says so when the file does not.
 */
import type { Metadata } from "next";

import { loadSprint, sprintSource } from "@/lib/artifacts/sprint";
import { fmtDec, fmtInt, fmtInterval, fmtSigned, isNum, outcomeName } from "@/lib/format/sprint";
import { CurveChart, IntervalChart } from "@/components/sprint/charts";
import { Section, SprintGate, SprintHeader, TableWrap, TD, TDR, TH, THR } from "@/components/sprint/SprintFrame";
import { KindTag, Txt, Val } from "@/components/sprint/Value";
import type { UpliftEval } from "@/lib/artifacts/sprint-types";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "스프린트 결과 · Uplift" };

type SelectionState = "selected" | "not_selected" | "loaded" | "absent";

/**
 * How the fitted method was decided, from metadata the file already has (#320 review): a loaded
 * model, a Validation-Qini choice, or no usable Validation Qini (the run then fits the default).
 */
function selectionState(a: UpliftEval): SelectionState {
  if (a.model_source || a.loaded_from) return "loaded";
  const sel = a.best_method_selection;
  if (!sel) return "absent";
  if (sel.best_method == null || a.tuning_report?.selection_ok === false) return "not_selected";
  return "selected";
}

function selectionNote(a: UpliftEval, state: SelectionState): string {
  const sel = a.best_method_selection;
  if (state === "loaded") {
    return `불러온 모델입니다 — 이 실행에서 다시 고르지 않았습니다(학습 실행 ${a.trained_run ?? "—"}).`;
  }
  if (state === "absent") return "이 결과 파일에는 학습 방법을 고른 기록이 없습니다.";
  if (state === "not_selected") {
    const why = a.tuning_report?.selection_reason ?? sel?.reason ?? "유효한 Validation Qini 가 없습니다";
    return `Validation Qini 로 고르지 못했습니다 — ${why}. 학습 방법은 기본값이고, 아래 '모델 비교'의 Test 지표도 선택 근거가 아닙니다.`;
  }
  const test = "'모델 비교'의 Test 지표는 고른 뒤 보고만 합니다(DR-303).";
  const grid = sel?.tuning?.grid;
  if (!Array.isArray(grid)) {
    return `학습 데이터 안에서 다시 떼어 낸 Validation 의 Qini 로 메타러너를 골랐습니다. 이 결과 파일에는 규제 선택 기록이 없어 아래 표는 메타러너별 점수만 보여 줍니다. ${test}`;
  }
  const learner = sel?.base_learner;
  let shown = "고른 규제";
  if (sel?.base_learner_is_current) {
    shown = "현행 규제";
  } else if (learner && Object.keys(learner).length > 0) {
    shown = `규제 ${Object.entries(learner)
      .map(([k, v]) => `${k}=${String(v)}`)
      .join(" · ")}`;
  }
  if (sel?.tuning?.enabled === false) {
    return `학습 데이터 안에서 다시 떼어 낸 Validation 의 Qini 로 메타러너를 골랐습니다(규제 후보가 하나라 규제는 고르지 않았습니다). 아래 표는 ${shown}에서의 메타러너별 점수입니다. ${test}`;
  }
  return `학습 데이터 안에서 다시 떼어 낸 Validation 의 Qini 로 메타러너 × 규제를 함께 골랐습니다. 아래 표는 ${shown}에서의 메타러너별 점수이고, 메타러너 × 규제 ${grid.length}개 조합 전체는 결과 파일의 tuning.grid 에 있습니다. ${test}`;
}

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
  const outcome = outcomeName(a.primary_outcome, a.outcome_window_days);
  const state = selectionState(a);

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

      <Section
        title="평균 처치 효과 (ATE · 95% 신뢰구간)"
        note={`${
          outcome.label === null
            ? "대조군(T0) 대비 차이입니다. 어느 결과의 차이인지 파일에 적혀 있지 않습니다."
            : `대조군(T0) 대비 ${outcome.label} 차이입니다.`
        } 구간이 0 을 포함하면 효과가 있다고 말할 수 없습니다.`}
      >
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

      <Section title="모델 선택" note={selectionNote(a, state)}>
        <p className="text-body-sm text-text">
          학습 방법 · <Txt text={a.fitted_method} /> (
          <Txt text={a.fitted_method_source} />)
        </p>
        {state === "selected" && a.best_method_selection?.validation_qini ? (
          <TableWrap label="Uplift 후보별 Validation Qini 표">
            <thead>
              <tr>
                <th className={TH}>방법</th>
                <th className={THR}>Validation Qini (선택 점수)</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(a.best_method_selection.validation_qini).map(([name, value]) => (
                <tr key={name}>
                  <td className={TD}>
                    {name}
                    {name === a.best_method_selection?.best_method ? " (확정)" : ""}
                  </td>
                  <td className={TDR}>
                    <Val text={fmtDec(value, 4)} />
                  </td>
                </tr>
              ))}
            </tbody>
          </TableWrap>
        ) : null}
        {state === "selected" ? (
          <p className="text-caption text-text-secondary">
            기준 · <Txt text={a.best_method_selection?.basis} />
          </p>
        ) : null}
      </Section>

      <Section title="모델 비교 — Test (선택 뒤 보고만)">
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
