#
# Copyright (c) 2026 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#
"""Pytest conftest - stub unavailable C extensions and modules."""

import sys
import types
from unittest.mock import MagicMock

# Stub fm_core (C extension not available in test env)
if 'fm_core' not in sys.modules:
    fm_core = types.ModuleType('fm_core')
    fm_core.FM_ALARM_ID = MagicMock()
    fm_core.FmAlarm = MagicMock()
    sys.modules['fm_core'] = fm_core

# Stub keyring if not available
if 'keyring' not in sys.modules:
    sys.modules['keyring'] = MagicMock()

# Ensure sysinv.helm.lifecycle_constants has the needed constants
try:
    from sysinv.helm.lifecycle_constants import LifecycleConstants  # noqa
except (ImportError, ModuleNotFoundError):
    lc_mod = types.ModuleType('sysinv.helm.lifecycle_constants')

    class LifecycleConstants:
        APP_LIFECYCLE_TYPE_SEMANTIC_CHECK = 'semantic_check'
        APP_LIFECYCLE_TYPE_OPERATION = 'operation'
        APP_LIFECYCLE_TIMING_PRE = 'pre'
        APP_LIFECYCLE_TIMING_POST = 'post'
        APP_LIFECYCLE_MODE_AUTO = 'auto'

    lc_mod.LifecycleConstants = LifecycleConstants
    sys.modules['sysinv.helm.lifecycle_constants'] = lc_mod
