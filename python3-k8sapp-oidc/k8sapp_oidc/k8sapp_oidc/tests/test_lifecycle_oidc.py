#
# Copyright (c) 2026 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#
# All Rights Reserved.
#
# This file was generated with AI assistance.
#

import os
import unittest
from unittest import mock

import yaml

from k8sapp_oidc.common import constants as app_constants
from k8sapp_oidc.lifecycle.lifecycle_oidc import OidcAppLifecycleOperator


class TestDumpOidcLoginConfig(unittest.TestCase):
    """Tests for _dump_oidc_login_config and its helper methods."""

    def setUp(self):
        self.operator = OidcAppLifecycleOperator.__new__(
            OidcAppLifecycleOperator
        )
        self.dbapi = mock.MagicMock()

    @mock.patch.object(OidcAppLifecycleOperator, '_get_issuer_ca_cert')
    @mock.patch.object(OidcAppLifecycleOperator, '_get_oidc_client_secret')
    @mock.patch.object(OidcAppLifecycleOperator, '_get_oidc_client_id')
    @mock.patch.object(OidcAppLifecycleOperator, '_get_k8s_issuer_url')
    def test_dump_writes_all_fields(self, mock_url, mock_id, mock_secret,
                                    mock_ca):
        mock_url.return_value = 'https://10.10.10.2:30556/dex'
        mock_id.return_value = 'stx-oidc-client-app'
        mock_secret.return_value = 'St8rlingX'
        mock_ca.return_value = 'FAKECERTBASE64=='

        tmp_dir = '/tmp/test_oidc_dump'
        os.makedirs(tmp_dir, exist_ok=True)
        config_path = os.path.join(tmp_dir, '.oidc_login_config')

        with mock.patch.object(app_constants, 'OIDC_LOGIN_CONFIG_FILE',
                               config_path):
            self.operator._dump_oidc_login_config(self.dbapi)

        self.assertTrue(os.path.exists(config_path))
        with open(config_path) as f:
            data = yaml.safe_load(f)

        self.assertEqual(data['oidc-issuer-url'],
                         'https://10.10.10.2:30556/dex')
        self.assertEqual(data['oidc-client-id'], 'stx-oidc-client-app')
        self.assertEqual(data['oidc-client-secret'], 'St8rlingX')
        self.assertEqual(data['oidc-issuer-ca'], 'FAKECERTBASE64==')

        # Verify permissions
        stat = os.stat(config_path)
        self.assertEqual(oct(stat.st_mode & 0o777), oct(0o644))

        # Cleanup
        os.unlink(config_path)
        os.rmdir(tmp_dir)

    @mock.patch.object(OidcAppLifecycleOperator, '_get_issuer_ca_cert')
    @mock.patch.object(OidcAppLifecycleOperator, '_get_oidc_client_secret')
    @mock.patch.object(OidcAppLifecycleOperator, '_get_oidc_client_id')
    @mock.patch.object(OidcAppLifecycleOperator, '_get_k8s_issuer_url')
    def test_dump_raises_when_issuer_url_missing(self, mock_url, mock_id,
                                                  mock_secret, mock_ca):
        from sysinv.common import exception
        mock_url.side_effect = exception.SysinvException("not found")
        mock_id.return_value = 'stx-oidc-client-app'
        mock_secret.return_value = 'St8rlingX'
        mock_ca.return_value = 'FAKECERTBASE64=='

        self.assertRaises(
            exception.SysinvException,
            self.operator._dump_oidc_login_config,
            self.dbapi,
        )

    @mock.patch.object(OidcAppLifecycleOperator, '_get_issuer_ca_cert')
    @mock.patch.object(OidcAppLifecycleOperator, '_get_oidc_client_secret')
    @mock.patch.object(OidcAppLifecycleOperator, '_get_oidc_client_id')
    @mock.patch.object(OidcAppLifecycleOperator, '_get_k8s_issuer_url')
    def test_dump_raises_when_client_id_empty(self, mock_url, mock_id,
                                              mock_secret, mock_ca):
        from sysinv.common import exception
        mock_url.return_value = 'https://10.10.10.2:30556/dex'
        mock_id.return_value = ''
        mock_secret.return_value = 'St8rlingX'
        mock_ca.return_value = 'FAKECERTBASE64=='

        self.assertRaises(
            exception.SysinvException,
            self.operator._dump_oidc_login_config,
            self.dbapi,
        )

    @mock.patch.object(OidcAppLifecycleOperator, '_get_issuer_ca_cert')
    @mock.patch.object(OidcAppLifecycleOperator, '_get_oidc_client_secret')
    @mock.patch.object(OidcAppLifecycleOperator, '_get_oidc_client_id')
    @mock.patch.object(OidcAppLifecycleOperator, '_get_k8s_issuer_url')
    def test_dump_raises_when_client_secret_empty(self, mock_url, mock_id,
                                                   mock_secret, mock_ca):
        from sysinv.common import exception
        mock_url.return_value = 'https://10.10.10.2:30556/dex'
        mock_id.return_value = 'stx-oidc-client-app'
        mock_secret.return_value = ''
        mock_ca.return_value = 'FAKECERTBASE64=='

        self.assertRaises(
            exception.SysinvException,
            self.operator._dump_oidc_login_config,
            self.dbapi,
        )

    @mock.patch.object(OidcAppLifecycleOperator, '_get_issuer_ca_cert')
    @mock.patch.object(OidcAppLifecycleOperator, '_get_oidc_client_secret')
    @mock.patch.object(OidcAppLifecycleOperator, '_get_oidc_client_id')
    @mock.patch.object(OidcAppLifecycleOperator, '_get_k8s_issuer_url')
    def test_dump_raises_when_ca_missing(self, mock_url, mock_id,
                                         mock_secret, mock_ca):
        from sysinv.common import exception
        mock_url.return_value = 'https://10.10.10.2:30556/dex'
        mock_id.return_value = 'stx-oidc-client-app'
        mock_secret.return_value = 'St8rlingX'
        mock_ca.side_effect = exception.SysinvException("no cert")

        self.assertRaises(
            exception.SysinvException,
            self.operator._dump_oidc_login_config,
            self.dbapi,
        )


class TestGetOidcClientId(unittest.TestCase):
    """Tests for _get_oidc_client_id."""

    def setUp(self):
        self.operator = OidcAppLifecycleOperator.__new__(
            OidcAppLifecycleOperator
        )
        self.dbapi = mock.MagicMock()

    def test_returns_configured_value(self):
        param = mock.MagicMock()
        param.value = 'custom-client-id'
        self.dbapi.service_parameter_get_one.return_value = param

        result = self.operator._get_oidc_client_id(self.dbapi)
        self.assertEqual(result, 'custom-client-id')

    def test_returns_default_when_not_found(self):
        from sysinv.common import exception
        self.dbapi.service_parameter_get_one.side_effect = \
            exception.NotFound()

        result = self.operator._get_oidc_client_id(self.dbapi)
        self.assertEqual(result, app_constants.DEFAULT_OIDC_CLIENT_ID)


class TestGetOidcClientSecret(unittest.TestCase):
    """Tests for _get_oidc_client_secret."""

    def setUp(self):
        self.operator = OidcAppLifecycleOperator.__new__(
            OidcAppLifecycleOperator
        )
        self.dbapi = mock.MagicMock()

    def test_returns_secret_from_user_overrides(self):
        db_app = mock.MagicMock()
        db_app.id = 1
        self.dbapi.kube_app_get.return_value = db_app

        override = mock.MagicMock()
        override.user_overrides = yaml.safe_dump(
            {'config': {'client_secret': 'my-custom-secret'}}
        )
        self.dbapi.helm_override_get.return_value = override

        result = self.operator._get_oidc_client_secret(self.dbapi)
        self.assertEqual(result, 'my-custom-secret')

    def test_returns_default_when_not_configured(self):
        db_app = mock.MagicMock()
        db_app.id = 1
        self.dbapi.kube_app_get.return_value = db_app

        override = mock.MagicMock()
        override.user_overrides = None
        self.dbapi.helm_override_get.return_value = override

        result = self.operator._get_oidc_client_secret(self.dbapi)
        self.assertEqual(result, app_constants.DEFAULT_OIDC_CLIENT_SECRET)


class TestGetIssuerCaCert(unittest.TestCase):
    """Tests for _get_issuer_ca_cert."""

    def setUp(self):
        self.operator = OidcAppLifecycleOperator.__new__(
            OidcAppLifecycleOperator
        )

    @mock.patch('k8sapp_oidc.lifecycle.lifecycle_oidc.dbapi')
    @mock.patch('k8sapp_oidc.lifecycle.lifecycle_oidc.client')
    @mock.patch.object(OidcAppLifecycleOperator, '_get_dex_tls_secret_name')
    def test_returns_ca_crt_from_dex_tls_secret(self, mock_get_secret_name,
                                                 mock_k8s_client,
                                                 mock_dbapi_mod):
        mock_get_secret_name.return_value = 'oidc-auth-apps-certificate'
        secret = mock.MagicMock()
        secret.data = {'ca.crt': 'BASE64CACERT=='}
        mock_k8s_client.CoreV1Api.return_value \
            .read_namespaced_secret.return_value = secret

        result = self.operator._get_issuer_ca_cert()
        self.assertEqual(result, 'BASE64CACERT==')
        mock_get_secret_name.assert_called_once()

    @mock.patch('k8sapp_oidc.lifecycle.lifecycle_oidc.dbapi')
    @mock.patch('k8sapp_oidc.lifecycle.lifecycle_oidc.client')
    @mock.patch.object(OidcAppLifecycleOperator, '_get_dex_tls_secret_name')
    def test_raises_when_no_ca_crt_in_secret(self, mock_get_secret_name,
                                              mock_k8s_client,
                                              mock_dbapi_mod):
        from sysinv.common import exception
        mock_get_secret_name.return_value = 'oidc-auth-apps-certificate'
        secret = mock.MagicMock()
        secret.data = {'tls.crt': 'BASE64TLS=='}
        mock_k8s_client.CoreV1Api.return_value \
            .read_namespaced_secret.return_value = secret

        self.assertRaises(
            exception.SysinvException,
            self.operator._get_issuer_ca_cert,
        )


class TestGetDexTlsSecretName(unittest.TestCase):
    """Tests for _get_dex_tls_secret_name."""

    def setUp(self):
        self.operator = OidcAppLifecycleOperator.__new__(
            OidcAppLifecycleOperator
        )
        self.dbapi = mock.MagicMock()

    def test_returns_secret_name_from_dex_overrides(self):
        db_app = mock.MagicMock()
        db_app.id = 1
        self.dbapi.kube_app_get.return_value = db_app

        overrides_data = {
            'volumeMounts': [
                {'mountPath': '/etc/ssl/certs/adcert', 'name': 'certdir'},
                {'mountPath': '/etc/dex/tls', 'name': 'https-tls'},
            ],
            'volumes': [
                {'name': 'certdir',
                 'secret': {'secretName': 'oidc-auth-apps-certificate'}},
                {'name': 'https-tls',
                 'secret': {'defaultMode': 420,
                            'secretName': 'my-custom-tls-secret'}},
            ],
        }
        override = mock.MagicMock()
        override.user_overrides = yaml.safe_dump(overrides_data)
        self.dbapi.helm_override_get.return_value = override

        result = self.operator._get_dex_tls_secret_name(self.dbapi)
        self.assertEqual(result, 'my-custom-tls-secret')

    def test_raises_when_no_volume_mount_for_dex_tls(self):
        from sysinv.common import exception
        db_app = mock.MagicMock()
        db_app.id = 1
        self.dbapi.kube_app_get.return_value = db_app

        overrides_data = {
            'volumeMounts': [
                {'mountPath': '/etc/ssl/certs/adcert', 'name': 'certdir'},
            ],
            'volumes': [
                {'name': 'certdir',
                 'secret': {'secretName': 'oidc-auth-apps-certificate'}},
            ],
        }
        override = mock.MagicMock()
        override.user_overrides = yaml.safe_dump(overrides_data)
        self.dbapi.helm_override_get.return_value = override

        self.assertRaises(
            exception.SysinvException,
            self.operator._get_dex_tls_secret_name,
            self.dbapi,
        )


class TestPostApplyOperation(unittest.TestCase):
    """Tests for post_apply_operation."""

    def setUp(self):
        self.operator = OidcAppLifecycleOperator.__new__(
            OidcAppLifecycleOperator
        )

    @mock.patch('k8sapp_oidc.lifecycle.lifecycle_oidc.dbapi')
    @mock.patch.object(OidcAppLifecycleOperator, '_dump_oidc_login_config')
    @mock.patch.object(OidcAppLifecycleOperator, '_load_kube_config')
    def test_post_apply_loads_kube_config_and_calls_dump(
            self, mock_kube, mock_dump, mock_dbapi_mod):
        mock_db = mock.MagicMock()
        mock_dbapi_mod.get_instance.return_value = mock_db

        self.operator.post_apply_operation(
            context=mock.MagicMock(),
            conductor_obj=mock.MagicMock(),
            app=mock.MagicMock(),
        )

        mock_kube.assert_called_once()
        mock_dump.assert_called_once_with(mock_db)


class TestValidateDexTlsSecret(unittest.TestCase):
    """Tests for _validate_dex_tls_secret."""

    def setUp(self):
        self.operator = OidcAppLifecycleOperator.__new__(
            OidcAppLifecycleOperator
        )
        self.dbapi = mock.MagicMock()

    @mock.patch('k8sapp_oidc.lifecycle.lifecycle_oidc.client')
    @mock.patch.object(OidcAppLifecycleOperator, '_get_dex_tls_secret_name')
    def test_passes_when_all_fields_present(self, mock_get_name, mock_k8s):
        mock_get_name.return_value = 'oidc-auth-apps-certificate'
        secret = mock.MagicMock()
        secret.data = {
            'ca.crt': 'BASE64CA==',
            'tls.crt': 'BASE64CERT==',
            'tls.key': 'BASE64KEY==',
        }
        mock_k8s.CoreV1Api.return_value \
            .read_namespaced_secret.return_value = secret

        # Should not raise
        self.operator._validate_dex_tls_secret(self.dbapi)

    @mock.patch('k8sapp_oidc.lifecycle.lifecycle_oidc.client')
    @mock.patch.object(OidcAppLifecycleOperator, '_get_dex_tls_secret_name')
    def test_raises_when_ca_crt_missing(self, mock_get_name, mock_k8s):
        from sysinv.common import exception
        mock_get_name.return_value = 'oidc-auth-apps-certificate'
        secret = mock.MagicMock()
        secret.data = {
            'tls.crt': 'BASE64CERT==',
            'tls.key': 'BASE64KEY==',
        }
        mock_k8s.CoreV1Api.return_value \
            .read_namespaced_secret.return_value = secret

        self.assertRaises(
            exception.SysinvException,
            self.operator._validate_dex_tls_secret,
            self.dbapi,
        )

    @mock.patch('k8sapp_oidc.lifecycle.lifecycle_oidc.client')
    @mock.patch.object(OidcAppLifecycleOperator, '_get_dex_tls_secret_name')
    def test_raises_when_tls_crt_missing(self, mock_get_name, mock_k8s):
        from sysinv.common import exception
        mock_get_name.return_value = 'oidc-auth-apps-certificate'
        secret = mock.MagicMock()
        secret.data = {
            'ca.crt': 'BASE64CA==',
            'tls.key': 'BASE64KEY==',
        }
        mock_k8s.CoreV1Api.return_value \
            .read_namespaced_secret.return_value = secret

        self.assertRaises(
            exception.SysinvException,
            self.operator._validate_dex_tls_secret,
            self.dbapi,
        )

    @mock.patch('k8sapp_oidc.lifecycle.lifecycle_oidc.client')
    @mock.patch.object(OidcAppLifecycleOperator, '_get_dex_tls_secret_name')
    def test_raises_when_tls_key_missing(self, mock_get_name, mock_k8s):
        from sysinv.common import exception
        mock_get_name.return_value = 'oidc-auth-apps-certificate'
        secret = mock.MagicMock()
        secret.data = {
            'ca.crt': 'BASE64CA==',
            'tls.crt': 'BASE64CERT==',
        }
        mock_k8s.CoreV1Api.return_value \
            .read_namespaced_secret.return_value = secret

        self.assertRaises(
            exception.SysinvException,
            self.operator._validate_dex_tls_secret,
            self.dbapi,
        )

    @mock.patch('k8sapp_oidc.lifecycle.lifecycle_oidc.client')
    @mock.patch.object(OidcAppLifecycleOperator, '_get_dex_tls_secret_name')
    def test_raises_when_all_fields_missing(self, mock_get_name, mock_k8s):
        from sysinv.common import exception
        mock_get_name.return_value = 'oidc-auth-apps-certificate'
        secret = mock.MagicMock()
        secret.data = {}
        mock_k8s.CoreV1Api.return_value \
            .read_namespaced_secret.return_value = secret

        self.assertRaises(
            exception.SysinvException,
            self.operator._validate_dex_tls_secret,
            self.dbapi,
        )

    @mock.patch('k8sapp_oidc.lifecycle.lifecycle_oidc.client')
    @mock.patch.object(OidcAppLifecycleOperator, '_get_dex_tls_secret_name')
    def test_raises_when_secret_read_fails(self, mock_get_name, mock_k8s):
        from sysinv.common import exception
        mock_get_name.return_value = 'oidc-auth-apps-certificate'
        mock_k8s.CoreV1Api.return_value \
            .read_namespaced_secret.side_effect = Exception("API error")

        self.assertRaises(
            exception.SysinvException,
            self.operator._validate_dex_tls_secret,
            self.dbapi,
        )

    @mock.patch('k8sapp_oidc.lifecycle.lifecycle_oidc.client')
    @mock.patch.object(OidcAppLifecycleOperator, '_get_dex_tls_secret_name')
    def test_raises_when_field_is_empty_string(self, mock_get_name, mock_k8s):
        from sysinv.common import exception
        mock_get_name.return_value = 'oidc-auth-apps-certificate'
        secret = mock.MagicMock()
        secret.data = {
            'ca.crt': '',
            'tls.crt': 'BASE64CERT==',
            'tls.key': 'BASE64KEY==',
        }
        mock_k8s.CoreV1Api.return_value \
            .read_namespaced_secret.return_value = secret

        self.assertRaises(
            exception.SysinvException,
            self.operator._validate_dex_tls_secret,
            self.dbapi,
        )


class TestValidateDexTlsSecretLocalDex(unittest.TestCase):
    """Tests for _validate_dex_tls_secret with a custom secret 'local-dex.tls'.

    Simulates a user-configured dex override that points to a different
    TLS secret name (local-dex.tls) which may be missing required fields.
    """

    def setUp(self):
        self.operator = OidcAppLifecycleOperator.__new__(
            OidcAppLifecycleOperator
        )
        self.dbapi = mock.MagicMock()

    @mock.patch('k8sapp_oidc.lifecycle.lifecycle_oidc.client')
    @mock.patch.object(OidcAppLifecycleOperator, '_get_dex_tls_secret_name')
    def test_local_dex_tls_passes_with_all_fields(self, mock_get_name,
                                                   mock_k8s):
        mock_get_name.return_value = 'local-dex.tls'
        secret = mock.MagicMock()
        secret.data = {
            'ca.crt': 'BASE64CA==',
            'tls.crt': 'BASE64CERT==',
            'tls.key': 'BASE64KEY==',
        }
        mock_k8s.CoreV1Api.return_value \
            .read_namespaced_secret.return_value = secret

        # Should not raise
        self.operator._validate_dex_tls_secret(self.dbapi)

    @mock.patch('k8sapp_oidc.lifecycle.lifecycle_oidc.client')
    @mock.patch.object(OidcAppLifecycleOperator, '_get_dex_tls_secret_name')
    def test_local_dex_tls_raises_missing_ca_crt(self, mock_get_name,
                                                  mock_k8s):
        from sysinv.common import exception
        mock_get_name.return_value = 'local-dex.tls'
        secret = mock.MagicMock()
        secret.data = {
            'tls.crt': 'BASE64CERT==',
            'tls.key': 'BASE64KEY==',
        }
        mock_k8s.CoreV1Api.return_value \
            .read_namespaced_secret.return_value = secret

        with self.assertRaises(exception.SysinvException) as ctx:
            self.operator._validate_dex_tls_secret(self.dbapi)
        self.assertIn('ca.crt', str(ctx.exception))
        self.assertIn('local-dex.tls', str(ctx.exception))

    @mock.patch('k8sapp_oidc.lifecycle.lifecycle_oidc.client')
    @mock.patch.object(OidcAppLifecycleOperator, '_get_dex_tls_secret_name')
    def test_local_dex_tls_raises_missing_tls_crt_and_key(self, mock_get_name,
                                                           mock_k8s):
        from sysinv.common import exception
        mock_get_name.return_value = 'local-dex.tls'
        secret = mock.MagicMock()
        secret.data = {
            'ca.crt': 'BASE64CA==',
        }
        mock_k8s.CoreV1Api.return_value \
            .read_namespaced_secret.return_value = secret

        with self.assertRaises(exception.SysinvException) as ctx:
            self.operator._validate_dex_tls_secret(self.dbapi)
        self.assertIn('tls.crt', str(ctx.exception))
        self.assertIn('tls.key', str(ctx.exception))

    @mock.patch('k8sapp_oidc.lifecycle.lifecycle_oidc.client')
    @mock.patch.object(OidcAppLifecycleOperator, '_get_dex_tls_secret_name')
    def test_local_dex_tls_raises_all_fields_missing(self, mock_get_name,
                                                      mock_k8s):
        from sysinv.common import exception
        mock_get_name.return_value = 'local-dex.tls'
        secret = mock.MagicMock()
        secret.data = {}
        mock_k8s.CoreV1Api.return_value \
            .read_namespaced_secret.return_value = secret

        with self.assertRaises(exception.SysinvException) as ctx:
            self.operator._validate_dex_tls_secret(self.dbapi)
        self.assertIn('ca.crt', str(ctx.exception))
        self.assertIn('tls.crt', str(ctx.exception))
        self.assertIn('tls.key', str(ctx.exception))

    @mock.patch('k8sapp_oidc.lifecycle.lifecycle_oidc.client')
    @mock.patch.object(OidcAppLifecycleOperator, '_get_dex_tls_secret_name')
    def test_local_dex_tls_raises_when_secret_not_found(self, mock_get_name,
                                                         mock_k8s):
        from sysinv.common import exception
        mock_get_name.return_value = 'local-dex.tls'
        mock_k8s.CoreV1Api.return_value \
            .read_namespaced_secret.side_effect = Exception("Not Found")

        with self.assertRaises(exception.SysinvException) as ctx:
            self.operator._validate_dex_tls_secret(self.dbapi)
        self.assertIn('local-dex.tls', str(ctx.exception))


class TestGetDexTlsSecretNameTrailingSlash(unittest.TestCase):
    """Tests for _get_dex_tls_secret_name with trailing slash in mountPath."""

    def setUp(self):
        self.operator = OidcAppLifecycleOperator.__new__(
            OidcAppLifecycleOperator
        )
        self.dbapi = mock.MagicMock()

    def _setup_overrides(self, mount_path, secret_name='my-tls-secret'):
        db_app = mock.MagicMock()
        db_app.id = 1
        self.dbapi.kube_app_get.return_value = db_app

        overrides_data = {
            'volumeMounts': [
                {'mountPath': mount_path, 'name': 'https-tls'},
            ],
            'volumes': [
                {'name': 'https-tls',
                 'secret': {'secretName': secret_name}},
            ],
        }
        override = mock.MagicMock()
        override.user_overrides = yaml.safe_dump(overrides_data)
        self.dbapi.helm_override_get.return_value = override

    def test_matches_path_without_trailing_slash(self):
        self._setup_overrides('/etc/dex/tls')
        result = self.operator._get_dex_tls_secret_name(self.dbapi)
        self.assertEqual(result, 'my-tls-secret')

    def test_matches_path_with_trailing_slash(self):
        self._setup_overrides('/etc/dex/tls/')
        result = self.operator._get_dex_tls_secret_name(self.dbapi)
        self.assertEqual(result, 'my-tls-secret')

    def test_does_not_match_unrelated_path(self):
        from sysinv.common import exception
        self._setup_overrides('/etc/dex/other')
        self.assertRaises(
            exception.SysinvException,
            self.operator._get_dex_tls_secret_name,
            self.dbapi,
        )

    def test_does_not_match_path_with_tls_prefix(self):
        from sysinv.common import exception
        self._setup_overrides('/etc/dex/tlsuchandsuch')
        self.assertRaises(
            exception.SysinvException,
            self.operator._get_dex_tls_secret_name,
            self.dbapi,
        )


class TestPreApplyCheck(unittest.TestCase):
    """Tests for pre_apply_check with TLS secret validation."""

    def setUp(self):
        self.operator = OidcAppLifecycleOperator.__new__(
            OidcAppLifecycleOperator
        )
        self.dbapi = mock.MagicMock()

    @mock.patch('k8sapp_oidc.lifecycle.lifecycle_oidc.dbapi')
    @mock.patch.object(OidcAppLifecycleOperator, '_validate_dex_tls_secret')
    @mock.patch.object(OidcAppLifecycleOperator,
                       '_is_oidc_overrides_fully_configured')
    @mock.patch.object(OidcAppLifecycleOperator, '_load_kube_config')
    def test_calls_validate_when_fully_configured(self, mock_kube,
                                                   mock_configured,
                                                   mock_validate,
                                                   mock_dbapi_mod):
        mock_dbapi_mod.get_instance.return_value = self.dbapi
        mock_configured.return_value = True

        self.operator.pre_apply_check(
            context=mock.MagicMock(),
            conductor_obj=mock.MagicMock(),
        )

        mock_validate.assert_called_once_with(self.dbapi)

    @mock.patch('k8sapp_oidc.lifecycle.lifecycle_oidc.dbapi')
    @mock.patch.object(OidcAppLifecycleOperator, '_validate_dex_tls_secret')
    @mock.patch.object(OidcAppLifecycleOperator,
                       '_is_oidc_overrides_fully_configured')
    @mock.patch.object(OidcAppLifecycleOperator, '_load_kube_config')
    def test_raises_when_validation_fails(self, mock_kube, mock_configured,
                                           mock_validate, mock_dbapi_mod):
        from sysinv.common import exception
        mock_dbapi_mod.get_instance.return_value = self.dbapi
        mock_configured.return_value = True
        mock_validate.side_effect = exception.SysinvException(
            "Dex TLS secret 'local-dex.tls' is missing required fields: "
            "ca.crt"
        )

        self.assertRaises(
            exception.SysinvException,
            self.operator.pre_apply_check,
            mock.MagicMock(),
            mock.MagicMock(),
        )

    @mock.patch('k8sapp_oidc.lifecycle.lifecycle_oidc.dbapi')
    @mock.patch.object(OidcAppLifecycleOperator,
                       '_extract_oam_ip_from_oidc_issuer_url')
    @mock.patch.object(OidcAppLifecycleOperator, '_get_k8s_issuer_url')
    @mock.patch.object(OidcAppLifecycleOperator, '_is_subcloud')
    @mock.patch.object(OidcAppLifecycleOperator, '_validate_dex_tls_secret')
    @mock.patch.object(OidcAppLifecycleOperator,
                       '_is_oidc_overrides_fully_configured')
    @mock.patch.object(OidcAppLifecycleOperator, '_load_kube_config')
    def test_skips_validation_when_not_fully_configured(
            self, mock_kube, mock_configured, mock_validate,
            mock_subcloud, mock_url, mock_extract, mock_dbapi_mod):
        mock_dbapi_mod.get_instance.return_value = self.dbapi
        mock_configured.return_value = False
        mock_subcloud.return_value = False
        mock_url.return_value = 'https://10.10.10.2:30556/dex'
        mock_extract.return_value = '10.10.10.2'

        self.operator.pre_apply_check(
            context=mock.MagicMock(),
            conductor_obj=mock.MagicMock(),
        )

        mock_validate.assert_not_called()
