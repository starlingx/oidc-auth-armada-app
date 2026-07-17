#
# Copyright (c) 2026 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#
# Lightweight test for py313 environment validation.
# Does not import sysinv or eventlet to avoid compatibility issues.

import unittest


class OidcTestCaseDummy(unittest.TestCase):
    """Basic smoke test for py313 environment."""

    def test_dummy(self):
        """Verify test infrastructure works on Python 3.13."""
        self.assertTrue(True)
