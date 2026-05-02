#
# Copyright (c) 2026 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

from unittest import TestCase

from k8sapp_oidc.common import constants as app_constants
from k8sapp_oidc.helm.dex_base import DEX_TLS_VERSION_MAP
from k8sapp_oidc.tests import test_plugins

from sysinv.common import constants
from sysinv.db import api as dbapi
from sysinv.helm import common
from sysinv.tests.db import base as dbbase
from sysinv.tests.db import utils as dbutils
from sysinv.tests.helm import base


# ---------------------------------------------------------------------------
# Pure unit tests (no DB required)
# ---------------------------------------------------------------------------

class TestDexTlsVersionMap(TestCase):
    """Tests for DEX_TLS_VERSION_MAP constant."""

    def test_tls12_maps_to_dex_format(self):
        self.assertEqual(
            DEX_TLS_VERSION_MAP[
                constants.SERVICE_PARAM_PLATFORM_TLS_VERSION_TLS12],
            '1.2')

    def test_tls13_maps_to_dex_format(self):
        self.assertEqual(
            DEX_TLS_VERSION_MAP[
                constants.SERVICE_PARAM_PLATFORM_TLS_VERSION_TLS13],
            '1.3')

    def test_map_has_exactly_two_entries(self):
        self.assertEqual(len(DEX_TLS_VERSION_MAP), 2)


# ---------------------------------------------------------------------------
# Helm override tests (DB-backed)
# ---------------------------------------------------------------------------

class DexTlsTestCase(test_plugins.K8SAppOidcAppMixin,
                     base.HelmTestCaseMixin):

    def setUp(self):
        super(DexTlsTestCase, self).setUp()
        self.app = dbutils.create_test_app(name='oidc-auth-apps')
        self.dbapi = dbapi.get_instance()

    def _get_dex_overrides(self):
        return self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_DEX,
            cnamespace=common.HELM_NS_KUBE_SYSTEM)

    def test_dex_default_tls_min_version(self):
        """Dex overrides include tlsMinVersion 1.2 by default."""
        overrides = self._get_dex_overrides()
        self.assertOverridesParameters(overrides, {
            'config': {
                'web': {
                    'tlsMinVersion': '1.2',
                },
            },
        })

    def test_dex_tls13_min_version(self):
        """Dex overrides reflect TLS 1.3 when service parameter is set."""
        dbutils.create_test_service_parameter(
            service=constants.SERVICE_TYPE_PLATFORM,
            section=constants.SERVICE_PARAM_SECTION_PLATFORM_CONFIG,
            name=constants.SERVICE_PARAM_NAME_PLATFORM_TLS_MIN_VERSION,
            value=constants.SERVICE_PARAM_PLATFORM_TLS_VERSION_TLS13)
        overrides = self._get_dex_overrides()
        self.assertOverridesParameters(overrides, {
            'config': {
                'web': {
                    'tlsMinVersion': '1.3',
                },
            },
        })


class DexTlsIPv4ControllerTestCase(DexTlsTestCase,
                                    dbbase.ProvisionedControllerHostTestCase):
    pass


class DexTlsIPv6AIODuplexTestCase(DexTlsTestCase,
                                   dbbase.BaseIPv6Mixin,
                                   dbbase.ProvisionedAIODuplexSystemTestCase):
    pass


class OidcClientTlsTestCase(test_plugins.K8SAppOidcAppMixin,
                             base.HelmTestCaseMixin):

    def setUp(self):
        super(OidcClientTlsTestCase, self).setUp()
        self.app = dbutils.create_test_app(name='oidc-auth-apps')
        self.dbapi = dbapi.get_instance()

    def _get_client_overrides(self):
        return self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_OIDC_CLIENT,
            cnamespace=common.HELM_NS_KUBE_SYSTEM)

    def test_client_default_tls_min_version(self):
        """OIDC Client overrides include tlsMinVersion 1.2 by default."""
        overrides = self._get_client_overrides()
        self.assertOverridesParameters(overrides, {
            'config': {
                'tlsMinVersion': '1.2',
            },
        })

    def test_client_default_cipher_suites(self):
        """OIDC Client overrides include default cipher suites as a list."""
        overrides = self._get_client_overrides()
        cipher_list = overrides['config']['tlsCipherSuites']
        self.assertIsInstance(cipher_list, list)
        self.assertTrue(len(cipher_list) > 0)
        # All default ciphers should be IANA format
        for cipher in cipher_list:
            self.assertTrue(cipher.startswith('TLS_'),
                            "Cipher %s not in IANA format" % cipher)

    def test_client_tls13_min_version(self):
        """OIDC Client overrides reflect TLS 1.3 when parameter is set."""
        dbutils.create_test_service_parameter(
            service=constants.SERVICE_TYPE_PLATFORM,
            section=constants.SERVICE_PARAM_SECTION_PLATFORM_CONFIG,
            name=constants.SERVICE_PARAM_NAME_PLATFORM_TLS_MIN_VERSION,
            value=constants.SERVICE_PARAM_PLATFORM_TLS_VERSION_TLS13)
        overrides = self._get_client_overrides()
        self.assertOverridesParameters(overrides, {
            'config': {
                'tlsMinVersion': '1.3',
            },
        })

    def test_client_custom_cipher_suites(self):
        """OIDC Client overrides reflect custom cipher suites."""
        custom_ciphers = ('TLS_AES_256_GCM_SHA384,'
                          'TLS_AES_128_GCM_SHA256')
        dbutils.create_test_service_parameter(
            service=constants.SERVICE_TYPE_PLATFORM,
            section=constants.SERVICE_PARAM_SECTION_PLATFORM_CONFIG,
            name=constants.SERVICE_PARAM_NAME_PLATFORM_TLS_CIPHER_SUITE,
            value=custom_ciphers)
        overrides = self._get_client_overrides()
        self.assertEqual(
            overrides['config']['tlsCipherSuites'],
            ['TLS_AES_256_GCM_SHA384', 'TLS_AES_128_GCM_SHA256'])

    def test_client_tls13_with_custom_ciphers(self):
        """OIDC Client overrides reflect both TLS 1.3 and custom ciphers."""
        dbutils.create_test_service_parameter(
            service=constants.SERVICE_TYPE_PLATFORM,
            section=constants.SERVICE_PARAM_SECTION_PLATFORM_CONFIG,
            name=constants.SERVICE_PARAM_NAME_PLATFORM_TLS_MIN_VERSION,
            value=constants.SERVICE_PARAM_PLATFORM_TLS_VERSION_TLS13)
        dbutils.create_test_service_parameter(
            service=constants.SERVICE_TYPE_PLATFORM,
            section=constants.SERVICE_PARAM_SECTION_PLATFORM_CONFIG,
            name=constants.SERVICE_PARAM_NAME_PLATFORM_TLS_CIPHER_SUITE,
            value='TLS_AES_256_GCM_SHA384')
        overrides = self._get_client_overrides()
        self.assertOverridesParameters(overrides, {
            'config': {
                'tlsMinVersion': '1.3',
            },
        })
        self.assertEqual(
            overrides['config']['tlsCipherSuites'],
            ['TLS_AES_256_GCM_SHA384'])


class OidcClientTlsIPv4ControllerTestCase(
        OidcClientTlsTestCase,
        dbbase.ProvisionedControllerHostTestCase):
    pass


class OidcClientTlsIPv6AIODuplexTestCase(
        OidcClientTlsTestCase,
        dbbase.BaseIPv6Mixin,
        dbbase.ProvisionedAIODuplexSystemTestCase):
    pass
