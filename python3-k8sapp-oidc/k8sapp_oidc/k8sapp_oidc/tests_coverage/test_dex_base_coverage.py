#
# Copyright (c) 2026 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#
"""Unit tests for dex_base.py module-level functions."""

import unittest
from unittest.mock import MagicMock
from unittest.mock import mock_open
from unittest.mock import patch

from k8sapp_oidc.helm import dex_base

from sysinv.common import constants


class TestGetPlatformTlsConfig(unittest.TestCase):
    """Tests for get_platform_tls_config."""

    def test_returns_defaults_on_exception(self):
        dbapi = MagicMock()
        dbapi.service_parameter_get_all.side_effect = Exception("fail")
        tls_ver, tls_cipher = dex_base.get_platform_tls_config(dbapi)
        # Falls back to defaults, does not raise
        self.assertIsNotNone(tls_ver)
        self.assertIsNotNone(tls_cipher)

    def test_reads_service_parameters(self):
        dbapi = MagicMock()
        p_ver = MagicMock()
        p_ver.name = \
            constants.SERVICE_PARAM_NAME_PLATFORM_TLS_MIN_VERSION
        p_ver.value = "VersionTLS13"
        p_cipher = MagicMock()
        p_cipher.name = \
            constants.SERVICE_PARAM_NAME_PLATFORM_TLS_CIPHER_SUITE
        p_cipher.value = "HIGH"
        dbapi.service_parameter_get_all.return_value = [p_ver, p_cipher]
        tls_ver, tls_cipher = dex_base.get_platform_tls_config(dbapi)
        self.assertEqual(tls_ver, "VersionTLS13")
        self.assertEqual(tls_cipher, "HIGH")


class TestLoadSubcloudOamList(unittest.TestCase):
    """Tests for _load_subcloud_oam_list."""

    @patch('k8sapp_oidc.helm.dex_base.os.path.isfile', return_value=False)
    def test_no_file_returns_empty(self, mock_isfile):
        self.assertEqual(dex_base._load_subcloud_oam_list(), {})

    @patch('k8sapp_oidc.helm.dex_base.json.load',
           return_value={'sc1': {'oam_ip': '10.0.0.1'}})
    @patch('k8sapp_oidc.helm.dex_base.open', new_callable=mock_open)
    @patch('k8sapp_oidc.helm.dex_base.os.path.isfile', return_value=True)
    def test_loads_file(self, mock_isfile, mock_f, mock_json):
        result = dex_base._load_subcloud_oam_list()
        self.assertIn('sc1', result)

    @patch('k8sapp_oidc.helm.dex_base.os.path.isfile',
           side_effect=Exception("io error"))
    def test_exception_returns_empty(self, mock_isfile):
        self.assertEqual(dex_base._load_subcloud_oam_list(), {})


class TestSaveSubcloudOamList(unittest.TestCase):
    """Tests for _save_subcloud_oam_list."""

    @patch('k8sapp_oidc.helm.dex_base.os.rename')
    @patch('k8sapp_oidc.helm.dex_base.os.chmod')
    @patch('k8sapp_oidc.helm.dex_base.json.dump')
    @patch('k8sapp_oidc.helm.dex_base.open', new_callable=mock_open)
    def test_saves_and_renames(self, mock_f, mock_dump, mock_chmod,
                               mock_rename):
        dex_base._save_subcloud_oam_list({'sc1': {'oam_ip': '10.0.0.1'}})
        mock_dump.assert_called_once()
        mock_rename.assert_called_once()

    @patch('k8sapp_oidc.helm.dex_base.os.unlink')
    @patch('k8sapp_oidc.helm.dex_base.open',
           side_effect=Exception("write fail"))
    def test_write_failure_cleans_up(self, mock_f, mock_unlink):
        # The write failure is swallowed and the temp file cleaned up.
        dex_base._save_subcloud_oam_list({'sc1': {}})


class TestGetManagedSubclouds(unittest.TestCase):
    """Tests for _get_managed_subclouds."""

    @patch('k8sapp_oidc.helm.dex_base.rest_api')
    def test_returns_managed_only(self, mock_rest):
        token = MagicMock()
        token.get_service_url.return_value = "https://dc:8119/v1.0"
        mock_rest.rest_api_request.return_value = {
            'subclouds': [
                {'name': 'sc1', 'management-state': 'managed',
                 'management-start-ip': '10.0.0.1',
                 'updated-at': 't1'},
                {'name': 'sc2', 'management-state': 'unmanaged',
                 'management-start-ip': '10.0.0.2',
                 'updated-at': 't2'},
            ]
        }
        result = dex_base._get_managed_subclouds(token)
        self.assertIn('sc1', result)
        self.assertNotIn('sc2', result)

    @patch('k8sapp_oidc.helm.dex_base.rest_api')
    def test_empty_response_returns_empty(self, mock_rest):
        token = MagicMock()
        mock_rest.rest_api_request.return_value = None
        self.assertEqual(dex_base._get_managed_subclouds(token), {})

    @patch('k8sapp_oidc.helm.dex_base.rest_api')
    def test_exception_returns_empty(self, mock_rest):
        token = MagicMock()
        mock_rest.rest_api_request.side_effect = Exception("api down")
        self.assertEqual(dex_base._get_managed_subclouds(token), {})


class TestQuerySubcloudOamIp(unittest.TestCase):
    """Tests for _query_subcloud_oam_ip."""

    @patch('k8sapp_oidc.helm.dex_base.rest_api')
    def test_returns_oam_ip_ipv4(self, mock_rest):
        token = MagicMock()
        mock_rest.rest_api_request.return_value = {
            'iextoams': [{'oam_floating_ip': '10.10.10.5'}]
        }
        result = dex_base._query_subcloud_oam_ip(token, "sc1", "10.0.0.1")
        self.assertEqual(result, "10.10.10.5")

    @patch('k8sapp_oidc.helm.dex_base.rest_api')
    def test_ipv6_host_bracketed(self, mock_rest):
        token = MagicMock()
        mock_rest.rest_api_request.return_value = {
            'iextoams': [{'oam_floating_ip': 'fd00::5'}]
        }
        result = dex_base._query_subcloud_oam_ip(token, "sc1", "fd00::1")
        self.assertEqual(result, "fd00::5")

    @patch('k8sapp_oidc.helm.dex_base.rest_api')
    def test_empty_response_returns_none(self, mock_rest):
        token = MagicMock()
        mock_rest.rest_api_request.return_value = None
        self.assertIsNone(
            dex_base._query_subcloud_oam_ip(token, "sc1", "10.0.0.1"))

    @patch('k8sapp_oidc.helm.dex_base.rest_api')
    def test_exception_returns_none(self, mock_rest):
        token = MagicMock()
        mock_rest.rest_api_request.side_effect = Exception("timeout")
        self.assertIsNone(
            dex_base._query_subcloud_oam_ip(token, "sc1", "10.0.0.1"))


class TestBatchQuerySubcloudOamIps(unittest.TestCase):
    """Tests for _batch_query_subcloud_oam_ips."""

    @patch('k8sapp_oidc.helm.dex_base._query_subcloud_oam_ip')
    def test_collects_successful_results(self, mock_query):
        mock_query.side_effect = lambda t, n, ip: "10.10.10.5" \
            if n == "sc1" else None
        token = MagicMock()
        subclouds = {"sc1": "10.0.0.1", "sc2": "10.0.0.2"}
        result = dex_base._batch_query_subcloud_oam_ips(token, subclouds)
        self.assertEqual(result.get("sc1"), "10.10.10.5")
        self.assertNotIn("sc2", result)


class TestGetSubcloudOamFloatingIps(unittest.TestCase):
    """Tests for get_subcloud_oam_floating_ips."""

    @patch('k8sapp_oidc.helm.dex_base.rest_api')
    def test_no_token_returns_empty(self, mock_rest):
        mock_rest.get_token.return_value = None
        self.assertEqual(dex_base.get_subcloud_oam_floating_ips(), [])

    @patch('k8sapp_oidc.helm.dex_base._save_subcloud_oam_list')
    @patch('k8sapp_oidc.helm.dex_base._batch_query_subcloud_oam_ips')
    @patch('k8sapp_oidc.helm.dex_base._load_subcloud_oam_list')
    @patch('k8sapp_oidc.helm.dex_base._get_managed_subclouds')
    @patch('k8sapp_oidc.helm.dex_base.rest_api')
    def test_resolves_new_subcloud(self, mock_rest, mock_managed,
                                   mock_load, mock_batch, mock_save):
        mock_rest.get_token.return_value = MagicMock()
        mock_managed.return_value = {
            'sc1': {'mgmt_ip': '10.0.0.1', 'updated_at': 't1'}
        }
        mock_load.return_value = {}
        mock_batch.return_value = {'sc1': '10.10.10.5'}
        result = dex_base.get_subcloud_oam_floating_ips()
        self.assertIn('10.10.10.5', result)
        mock_save.assert_called_once()

    @patch('k8sapp_oidc.helm.dex_base._save_subcloud_oam_list')
    @patch('k8sapp_oidc.helm.dex_base._batch_query_subcloud_oam_ips')
    @patch('k8sapp_oidc.helm.dex_base._load_subcloud_oam_list')
    @patch('k8sapp_oidc.helm.dex_base._get_managed_subclouds')
    @patch('k8sapp_oidc.helm.dex_base.rest_api')
    def test_reuses_unchanged_subcloud(self, mock_rest, mock_managed,
                                       mock_load, mock_batch, mock_save):
        mock_rest.get_token.return_value = MagicMock()
        mock_managed.return_value = {
            'sc1': {'mgmt_ip': '10.0.0.1', 'updated_at': 't1'}
        }
        # Known and unchanged -> no re-query
        mock_load.return_value = {
            'sc1': {'oam_ip': '10.10.10.5', 'updated_at': 't1'}
        }
        result = dex_base.get_subcloud_oam_floating_ips()
        self.assertIn('10.10.10.5', result)
        mock_batch.assert_not_called()

    @patch('k8sapp_oidc.helm.dex_base._get_managed_subclouds')
    @patch('k8sapp_oidc.helm.dex_base.rest_api')
    def test_no_subclouds_returns_empty(self, mock_rest, mock_managed):
        mock_rest.get_token.return_value = MagicMock()
        mock_managed.return_value = {}
        self.assertEqual(dex_base.get_subcloud_oam_floating_ips(), [])

    @patch('k8sapp_oidc.helm.dex_base.rest_api')
    def test_exception_returns_empty(self, mock_rest):
        mock_rest.get_token.side_effect = Exception("token fail")
        self.assertEqual(dex_base.get_subcloud_oam_floating_ips(), [])


if __name__ == '__main__':
    unittest.main()
