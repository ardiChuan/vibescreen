import dataclasses
import unittest

from tools.tokenserver.interaction_types import (
    InteractionProvider,
    InteractionResult,
)


class InteractionTypeTests(unittest.TestCase):
    def test_result_is_provider_neutral_and_immutable(self):
        result = InteractionResult(verdict="approve", option_index=1)
        self.assertEqual(result.verdict, "approve")
        self.assertEqual(result.option_index, 1)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            result.verdict = "deny"

    def test_provider_wire_values_are_stable(self):
        self.assertEqual(InteractionProvider.CLAUDE.value, "claude")
        self.assertEqual(InteractionProvider.CODEX.value, "codex")

    def test_result_rejects_unsupported_verdict(self):
        with self.assertRaisesRegex(ValueError, "unsupported verdict"):
            InteractionResult(verdict="maybe")

    def test_result_rejects_negative_option_index(self):
        with self.assertRaisesRegex(ValueError, "negative option index"):
            InteractionResult(verdict="approve", option_index=-1)
