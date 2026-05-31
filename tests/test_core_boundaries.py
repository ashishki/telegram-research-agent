import inspect
import sys
import types
import unittest


def _install_stub(module_name: str, **attributes: object) -> None:
    module = sys.modules.get(module_name)
    if module is None:
        module = types.ModuleType(module_name)
        sys.modules[module_name] = module
    for name, value in attributes.items():
        setattr(module, name, value)


_install_stub(
    "anthropic",
    APIConnectionError=Exception,
    APIStatusError=Exception,
    APITimeoutError=Exception,
    Anthropic=object,
    RateLimitError=Exception,
)
_install_stub("weasyprint")
_install_stub("jinja2")
_install_stub("numpy", asarray=lambda value: value)
_install_stub("sklearn")
_install_stub("sklearn.cluster", KMeans=object)
_install_stub("sklearn.feature_extraction")
_install_stub("sklearn.feature_extraction.text", ENGLISH_STOP_WORDS=set(), TfidfVectorizer=object)
_install_stub("sklearn.metrics", silhouette_score=lambda *_args, **_kwargs: 0.0)

import output.generate_digest as generate_digest
import proof_receipts


class TestCoreBoundaries(unittest.TestCase):
    def test_digest_generation_keeps_core_as_derived_vocabulary(self):
        source = inspect.getsource(generate_digest)

        self.assertIn("build_core_research_brief_receipt", source)
        self.assertIn("core_receipt_sha256", source)
        self.assertNotIn("verify_core_research_brief_evidence_refs", source)
        self.assertNotIn("entropy_core", source.replace("entropy_core.product_receipt.v1", ""))

    def test_proof_receipts_do_not_own_local_receipt_state(self):
        source = inspect.getsource(proof_receipts)

        self.assertNotIn("record_research_brief_receipt", source)
        self.assertNotIn("update_research_brief_receipt_delivery_refs", source)
        self.assertNotIn("review_research_brief_receipt", source)
        self.assertNotIn("weekly_usefulness_logs", source)
        self.assertNotIn("telegram_delivery_timestamp", source)


if __name__ == "__main__":
    unittest.main()
