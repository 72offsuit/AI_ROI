from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.measurement import sink as sk
from src.simulator import api
from src.simulator._internal import guardrails, profiles, runtime, storage
from src.simulator._internal import world as wd

EXIT_OK = 0
EXIT_SIMULATOR_ERROR = 1
EXIT_BAD_ARGUMENT = 2

_CUSTOMERS_HELP = "생략하면 프로파일 기본 고객 수(기본값이 없는 프로파일은 생략할 수 없다)"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m src.simulator",
        description="시뮬레이터 세계를 만들고 진행하고 이어간다. 성공하면 저장한 state_id 를 출력한다.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init", help="새 세계를 만들고(선택적으로 N 일 진행) 상태를 저장한다")
    init.add_argument("--seed", type=int, required=True)
    init.add_argument("--customers", type=int, default=None, help=_CUSTOMERS_HELP)
    init.add_argument("--profile", required=True)
    init.add_argument("--output-root", required=True)
    init.add_argument("--days", type=int, default=0)

    advance = commands.add_parser("advance", help="출력 루트의 계보 머리 상태를 불러 N 일 진행하고 저장한다")
    advance.add_argument("--output-root", required=True)
    advance.add_argument("--days", type=int, required=True)

    resume = commands.add_parser("resume", help="지정한 상태를 불러 N 일 진행하고 저장한다")
    resume.add_argument("--state-id", required=True)
    resume.add_argument("--output-root", required=True)
    resume.add_argument("--days", type=int, required=True)

    checks = commands.add_parser(
        "guardrails",
        help="새 세계를 워밍업한 시점에서 이탈률·ATE·쿠폰 사용률·Sleeping Dog 을 검사해 숨김 영역에 쓰고 표로 낸다",
    )
    checks.add_argument("--seed", type=int, required=True)
    checks.add_argument("--customers", type=int, default=None, help=_CUSTOMERS_HELP)
    checks.add_argument("--profile", default="small")
    checks.add_argument("--warmup-days", type=int, required=True)
    checks.add_argument("--sample", type=int, default=None)
    checks.add_argument("--output-root", required=True)

    for command in (init, advance, resume, checks):
        command.add_argument(
            "--config", default=None,
            help="실험용 생성 설정 파일. 생략하면 기본 설정. 이어가는 명령은 그 상태를 만든 파일을 다시 준다",
        )
        command.add_argument("--hidden-root", default=None, help="테스트·도구 전용")
    return parser


def _customers(args: argparse.Namespace) -> int:
    """`--customers` 를 생략했으면 프로파일 기본 고객 수를 쓴다. 기본값이 없는(모르는 것 포함) profile 이면
    `ValueError`(종료 코드 2)다. API 는 기본값을 쓰지 않는다(DR-S3-p6-signup U11)."""
    if args.customers is not None:
        return args.customers
    found = profiles.default_customers(args.profile)
    if found is None:
        raise ValueError(f"프로파일 {args.profile!r} 은 기본 고객 수가 없다 — --customers 를 준다")
    return found


def _guardrails(args: argparse.Namespace) -> int:
    customers = _customers(args)
    api.init(
        args.seed, customers, args.profile, args.output_root,
        hidden_root=args.hidden_root, config_path=args.config,
    )
    summary = api.advance(args.warmup_days)
    session = runtime.active
    orders = storage.read_orders(session.hidden_root, str(summary.run_id)) or []
    result, rows = guardrails.evaluate(session.world, orders, args.sample)
    result.update(seed=args.seed, customers=customers, profile=args.profile,
                  warmup_days=args.warmup_days, simulator_version=session.world["simulator_version"])
    root = storage.ground_truth_root(session.hidden_root).joinpath("guardrails")
    name = f"guardrails-{session.world['world_id']}-d{args.warmup_days}"
    guardrails.write(root, result, rows, name)
    print(guardrails.table(result))
    return EXIT_OK


def _head_state_id(output_root: str, hidden_root: str | None) -> str:
    root = Path(output_root).resolve()
    head = sk.latest_run_id(root)
    if head is None:
        raise api.OutputRootError(
            f"{root} 에 계보 머리가 없다 — 빈 루트이거나 사슬이 갈라졌다. resume --state-id 를 쓴다"
        )
    hidden = storage.default_hidden_root() if hidden_root is None else Path(hidden_root).resolve()
    try:
        record = storage.read_sidecar(hidden, head)
        if record is None:
            raise api.OutputRootError(f"계보 머리 {head} 의 시뮬레이터 계보 기록이 없다")
        end_digest = record["end_state_digest"]
        if not isinstance(end_digest, str):
            raise TypeError("end_state_digest 가 문자열이 아니다")
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise api.OutputRootError(
            f"계보 머리 {head} 의 시뮬레이터 계보 기록이 손상됐다: {type(error).__name__}"
        ) from error
    return wd.state_id(end_digest)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "guardrails":
            return _guardrails(args)
        if args.command == "init":
            api.init(
                args.seed, _customers(args), args.profile, args.output_root,
                hidden_root=args.hidden_root, config_path=args.config,
            )
        else:
            state_id = (
                args.state_id if args.command == "resume"
                else _head_state_id(args.output_root, args.hidden_root)
            )
            api.load_state(
                state_id, args.output_root, hidden_root=args.hidden_root, config_path=args.config
            )
        api.advance(args.days)
        print(api.save_state())
    except api.SimulatorError as error:
        print(f"오류: {error}", file=sys.stderr)
        return EXIT_SIMULATOR_ERROR
    except (TypeError, ValueError) as error:
        print(f"인자 오류: {error}", file=sys.stderr)
        return EXIT_BAD_ARGUMENT
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
