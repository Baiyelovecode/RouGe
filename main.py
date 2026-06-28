from __future__ import annotations

import argparse

from game.auto_player import run_auto
from game.catalog import print_full_card_catalog, print_full_relic_catalog
from game.runner import Game


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="数值之塔 CLI 原型")
    parser.add_argument("--auto", action="store_true", help="启用自动玩家")
    parser.add_argument("--role", choices=["exile", "toxicist", "burner"], default="exile")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--combats", type=int, default=1)
    parser.add_argument("--max-actions", type=int, default=200)
    parser.add_argument("--agent", choices=["heuristic", "llm"], default="heuristic")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--cards", action="store_true", help="打印完整卡牌图鉴")
    parser.add_argument("--relics", action="store_true", help="打印完整遗物图鉴")
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    if args.cards:
        print_full_card_catalog()
        return
    if args.relics:
        print_full_relic_catalog()
        return
    if args.auto:
        run_auto(
            role_id=args.role,
            seed=args.seed,
            combats=args.combats,
            max_actions=args.max_actions,
            verbose=not args.quiet,
            agent_name=args.agent,
        )
        return

    try:
        Game().run()
    except KeyboardInterrupt:
        print("\n已退出游戏。")
    except EOFError:
        print("\n输入流已关闭，游戏被终端提前结束。请直接在交互式终端中运行 python main.py。")


if __name__ == "__main__":
    main()
