#
# Copyright (c) 2026 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#
"""Shared test helper functions for oidc-auth-armada-app."""

from unittest.mock import MagicMock

from k8sapp_oidc.tests_coverage import fixture_data as tc


def create_mock_dbapi():
    """Create a mock dbapi instance with standard methods.

    Returns:
        MagicMock configured as a dbapi instance.
    """
    dbapi_instance = MagicMock()

    # Mock kube_app_get
    mock_app = MagicMock()
    mock_app.id = 1
    mock_app.name = tc.APP_NAME
    dbapi_instance.kube_app_get.return_value = mock_app

    # Mock isystem_get_one
    mock_system = MagicMock()
    mock_system.system_mode = "duplex"
    mock_system.distributed_cloud_role = None
    dbapi_instance.isystem_get_one.return_value = mock_system

    return dbapi_instance


def create_mock_helm_override(user_overrides=None,
                              system_overrides=None):
    """Create a mock helm override object.

    Args:
        user_overrides: User override string or None.
        system_overrides: System override dict or None.

    Returns:
        MagicMock configured as a helm override.
    """
    override = MagicMock()
    override.user_overrides = user_overrides
    override.system_overrides = system_overrides or {}
    return override


def create_mock_network(pool_uuid="test-pool-uuid"):
    """Create a mock network object.

    Args:
        pool_uuid: UUID for the address pool.

    Returns:
        MagicMock configured as a network.
    """
    net = MagicMock()
    net.pool_uuid = pool_uuid
    return net


def create_mock_address_pool(floating_address=None):
    """Create a mock address pool object.

    Args:
        floating_address: The floating IP address string.

    Returns:
        MagicMock configured as an address pool.
    """
    pool = MagicMock()
    pool.floating_address = floating_address or tc.OAM_IP_V4
    return pool
