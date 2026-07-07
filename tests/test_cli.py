import unittest

from main import build_parser


class TestCli(unittest.TestCase):
    def test_bootstrap_accepts_days_window(self):
        args = build_parser().parse_args(["bootstrap", "--days", "84"])

        self.assertEqual(args.days, 84)

    def test_bootstrap_rejects_non_positive_days_window(self):
        with self.assertRaises(SystemExit):
            build_parser().parse_args(["bootstrap", "--days", "0"])


if __name__ == "__main__":
    unittest.main()
