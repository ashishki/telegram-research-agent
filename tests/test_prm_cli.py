from prm.cli import build_parser


def test_cli_commands():
    parser = build_parser()
    assert parser.parse_args(["assistant"]).command == "assistant"
    assert parser.parse_args(["research", "question"]).command == "research"
    assert parser.parse_args(["brief", "question"]).command == "brief"
    assert parser.parse_args(["chat", "question"]).command == "chat"
