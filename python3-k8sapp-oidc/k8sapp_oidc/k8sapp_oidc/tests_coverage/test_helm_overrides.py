#
# Copyright (c) 2026 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#
"""Unit tests for helm override modules."""

import unittest
from unittest.mock import MagicMock

from k8sapp_oidc.common import constants as app_constants
from k8sapp_oidc.helm.dex import Dex
from k8sapp_oidc.helm.dex_base import DexBaseHelm
from k8sapp_oidc.helm.oidc_client import OidcClientHelm
from k8sapp_oidc.helm.secret_observer import SecretObserverHelm
from k8sapp_oidc.tests_coverage import fixture_data as tc
from sysinv.common import exception


class TestDexBaseHelm(unittest.TestCase):
    """Tests for DexBaseHelm base class."""

    def _create_instance(self):
        """Create a DexBaseHelm subclass instance for testing."""
        class TestDex(DexBaseHelm):
            """Concrete subclass for testing."""

            CHART = "test-chart"

            def __init__(self):
                """Skip parent __init__."""

        return TestDex()

    def test_chart_constants(self):
        """Test port constants are defined correctly."""
        instance = self._create_instance()
        self.assertEqual(instance.OIDC_CLIENT_NODE_PORT, 30555)
        self.assertEqual(instance.DEX_NODE_PORT, 30556)
        self.assertEqual(instance.OAUTH2_PROXY_PORT, 5000)

    def test_get_client_id(self):
        """Test _get_client_id returns expected value."""
        instance = self._create_instance()
        self.assertEqual(
            instance._get_client_id(), 'stx-oidc-client-app')

    def test_get_client_secret(self):
        """Test _get_client_secret returns expected value."""
        instance = self._create_instance()
        self.assertEqual(instance._get_client_secret(), 'St8rlingX')

    def test_get_namespaces(self):
        """Test get_namespaces returns supported namespaces."""
        instance = self._create_instance()
        self.assertIn('kube-system', instance.get_namespaces())

    def test_chart_property_raises(self):
        """Test CHART property raises in base class."""
        class NoCHART(DexBaseHelm):
            """Subclass without CHART defined."""

            def __init__(self):
                """Skip parent init."""

        instance = NoCHART()
        with self.assertRaises(NotImplementedError):
            _ = instance.CHART


class TestDexHelm(unittest.TestCase):
    """Tests for Dex helm override class."""

    def _create_instance(self):
        """Create Dex instance with mocked parent methods."""
        instance = Dex.__new__(Dex)
        instance._operator = MagicMock()
        instance._format_url_address = MagicMock(
            return_value=tc.OAM_IP_V4)
        instance._get_oam_address = MagicMock(
            return_value=tc.OAM_IP_V4)
        instance._num_replicas_for_platform_app = MagicMock(
            return_value=2)
        return instance

    def test_chart_name(self):
        """Test CHART is set to 'dex'."""
        self.assertEqual(Dex.CHART, tc.CHART_DEX)

    def test_get_overrides_kube_system(self):
        """Test overrides for kube-system namespace."""
        instance = self._create_instance()
        overrides = instance.get_overrides(namespace='kube-system')
        self.assertIn('config', overrides)
        self.assertIn('issuer', overrides['config'])
        self.assertEqual(overrides['replicaCount'], 2)

    def test_get_overrides_all_namespaces(self):
        """Test overrides returns dict when no namespace."""
        instance = self._create_instance()
        overrides = instance.get_overrides(namespace=None)
        self.assertIn('kube-system', overrides)

    def test_get_overrides_invalid_namespace(self):
        """Test raises for invalid namespace."""
        instance = self._create_instance()
        self.assertRaises(
            exception.InvalidHelmNamespace,
            instance.get_overrides, namespace='invalid-ns')

    def test_static_clients_structure(self):
        """Test _get_static_clients returns proper structure."""
        instance = self._create_instance()
        clients = instance._get_static_clients()
        self.assertEqual(len(clients), 1)
        self.assertEqual(clients[0]['id'], 'stx-oidc-client-app')
        self.assertEqual(len(clients[0]['redirectURIs']), 2)

    def test_issuer_url_format(self):
        """Test issuer URL is correctly formatted."""
        instance = self._create_instance()
        overrides = instance.get_overrides(namespace='kube-system')
        expected = "https://%s:%s/dex" % (
            tc.OAM_IP_V4, tc.DEX_NODE_PORT)
        self.assertEqual(overrides['config']['issuer'], expected)

    def test_service_node_port(self):
        """Test service nodePort is set correctly."""
        instance = self._create_instance()
        overrides = instance.get_overrides(namespace='kube-system')
        self.assertEqual(
            overrides['service']['ports']['https']['nodePort'],
            tc.DEX_NODE_PORT)


class TestOidcClientHelm(unittest.TestCase):
    """Tests for OidcClientHelm override class."""

    def _create_instance(self):
        """Create OidcClientHelm with mocked parent methods."""
        instance = OidcClientHelm.__new__(OidcClientHelm)
        instance._operator = MagicMock()
        instance._format_url_address = MagicMock(
            return_value=tc.OAM_IP_V4)
        instance._get_oam_address = MagicMock(
            return_value=tc.OAM_IP_V4)
        instance._num_replicas_for_platform_app = MagicMock(
            return_value=1)
        return instance

    def test_chart_name(self):
        """Test CHART is set to 'oidc-client'."""
        self.assertEqual(
            OidcClientHelm.CHART, tc.CHART_OIDC_CLIENT)

    def test_service_name(self):
        """Test SERVICE_NAME is set."""
        self.assertEqual(OidcClientHelm.SERVICE_NAME, 'oidc_client')

    def test_get_overrides_kube_system(self):
        """Test overrides for kube-system namespace."""
        instance = self._create_instance()
        overrides = instance.get_overrides(namespace='kube-system')
        self.assertIn('config', overrides)
        self.assertIn('service', overrides)
        self.assertEqual(overrides['replicas'], 1)

    def test_config_values(self):
        """Test config contains required keys."""
        instance = self._create_instance()
        overrides = instance.get_overrides(namespace='kube-system')
        config = overrides['config']
        self.assertEqual(config['client_id'], 'stx-oidc-client-app')
        self.assertEqual(config['client_secret'], 'St8rlingX')

    def test_get_overrides_invalid_namespace(self):
        """Test raises for invalid namespace."""
        instance = self._create_instance()
        self.assertRaises(
            exception.InvalidHelmNamespace,
            instance.get_overrides, namespace='invalid-ns')

    def test_get_overrides_no_namespace(self):
        """Test returns all overrides when namespace is None."""
        instance = self._create_instance()
        overrides = instance.get_overrides(namespace=None)
        self.assertIn('kube-system', overrides)


class TestSecretObserverHelm(unittest.TestCase):
    """Tests for SecretObserverHelm override class."""

    def _create_instance(self):
        """Create SecretObserverHelm with mocked parent."""
        instance = SecretObserverHelm.__new__(SecretObserverHelm)
        instance._operator = MagicMock()
        return instance

    def test_chart_name(self):
        """Test CHART is set to 'secret-observer'."""
        self.assertEqual(
            SecretObserverHelm.CHART, tc.CHART_SECRET_OBSERVER)

    def test_service_name(self):
        """Test SERVICE_NAME is set."""
        self.assertEqual(
            SecretObserverHelm.SERVICE_NAME, 'secret-observer')

    def test_get_overrides_kube_system(self):
        """Test overrides for kube-system returns empty dict."""
        instance = self._create_instance()
        self.assertEqual(
            instance.get_overrides(namespace='kube-system'), {})

    def test_get_overrides_invalid_namespace(self):
        """Test raises for invalid namespace."""
        instance = self._create_instance()
        self.assertRaises(
            exception.InvalidHelmNamespace,
            instance.get_overrides, namespace='invalid-ns')

    def test_get_overrides_no_namespace(self):
        """Test returns all overrides when namespace is None."""
        instance = self._create_instance()
        overrides = instance.get_overrides(namespace=None)
        self.assertIn('kube-system', overrides)


class TestConstants(unittest.TestCase):
    """Tests for common constants module."""

    def test_helm_chart_dex(self):
        """Test HELM_CHART_DEX constant."""
        self.assertEqual(app_constants.HELM_CHART_DEX, 'dex')

    def test_helm_chart_oidc_client(self):
        """Test HELM_CHART_OIDC_CLIENT constant."""
        self.assertEqual(
            app_constants.HELM_CHART_OIDC_CLIENT, 'oidc-client')

    def test_helm_chart_secret_observer(self):
        """Test HELM_CHART_SECRET_OBSERVER constant."""
        self.assertEqual(
            app_constants.HELM_CHART_SECRET_OBSERVER,
            'secret-observer')
