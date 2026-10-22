/** Sprint result screens (issue 147) — one list shared by the sidebar and the overview. */
import type { SprintFileName } from "@/lib/artifacts/sprint-types";

export const SPRINT_ROUTES: { href: string; label: string; files: SprintFileName[] }[] = [
  { href: "/sprint", label: "개요", files: ["run_meta"] },
  { href: "/sprint/churn", label: "이탈 예측", files: ["churn_eval", "clv_eval"] },
  { href: "/sprint/uplift", label: "Uplift", files: ["uplift_eval"] },
  { href: "/sprint/segments", label: "세그먼트", files: ["segments"] },
  { href: "/sprint/strategy", label: "전략·ROI", files: ["strategy_comparison"] },
  { href: "/sprint/ab", label: "A/B", files: ["ab_test"] },
  { href: "/sprint/grounding", label: "데이터 근거", files: ["realism_report"] },
];
