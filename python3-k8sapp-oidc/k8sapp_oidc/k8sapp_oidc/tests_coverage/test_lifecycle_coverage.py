#
# Copyright (c) 2026 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#
"""Unit tests for lifecycle_oidc.py."""

import unittest
from unittest.mock import MagicMock
from unittest.mock import patch

from k8sapp_oidc.lifecycle.lifecycle_oidc import OidcAppLifecycleOperator
from sysinv.common import constants
from sysinv.common import exception
from sysinv.helm.lifecycle_constants import LifecycleConstants as Lc


def _create_operator():
    """Create an OidcAppLifecycleOperator with mocked internals."""
    op = OidcAppLifecycleOperator.__new__(OidcAppLifecycleOperator)
    op._operator = MagicMock()
    return op


class TestExtractOamIp(unittest.TestCase):
    """Tests for _extract_oam_ip_from_oidc_issuer_url."""

    def setUp(self):
        self.op = _create_operator()

    def test_extract_ipv4(self):
        result = self.op._extract_oam_ip_from_oidc_issuer_url(
            "https://10.10.10.2:30556/dex")
        self.assertEqual(result, "10.10.10.2")

    def test_extract_ipv6(self):
        result = self.op._extract_oam_ip_from_oidc_issuer_url(
            "https://[fd01::2]:30556/dex")
        self.assertEqual(result, "fd01::2")

    def test_invalid_url_raises(self):
        with self.assertRaises(exception.SysinvException):
            self.op._extract_oam_ip_from_oidc_issuer_url("not-a-url")

    def test_http_url_raises(self):
        with self.assertRaises(exception.SysinvException):
            self.op._extract_oam_ip_from_oidc_issuer_url(
                "http://10.10.10.2:30556/dex")


class TestIsSubcloud(unittest.TestCase):
    """Tests for _is_subcloud."""

    def setUp(self):
        self.op = _create_operator()

    def test_is_subcloud_true(self):
        dbapi = MagicMock()
        system = MagicMock()
        system.distributed_cloud_role = \
            constants.DISTRIBUTED_CLOUD_ROLE_SUBCLOUD
        dbapi.isystem_get_one.return_value = system
        self.assertTrue(self.op._is_subcloud(dbapi))

    def test_is_subcloud_false(self):
        dbapi = MagicMock()
        system = MagicMock()
        system.distributed_cloud_role = "controller"
        dbapi.isystem_get_one.return_value = system
        self.assertFalse(self.op._is_subcloud(dbapi))

    def test_is_subcloud_exception(self):
        dbapi = MagicMock()
        dbapi.isystem_get_one.side_effect = Exception("db error")
        with self.assertRaises(exception.SysinvException):
            self.op._is_subcloud(dbapi)


class TestGetFloatingIp(unittest.TestCase):
    """Tests for _get_floating_ip_by_net_type."""

    def setUp(self):
        self.op = _create_operator()

    def test_get_oam_ip(self):
        dbapi = MagicMock()
        network = MagicMock()
        network.pool_uuid = "pool-uuid-1"
        dbapi.network_get_by_type.return_value = network
        addr_pool = MagicMock()
        addr_pool.floating_address = "10.10.10.2"
        dbapi.address_pool_get.return_value = addr_pool
        result = self.op._get_floating_ip_by_net_type(
            dbapi, constants.NETWORK_TYPE_OAM)
        self.assertEqual(result, "10.10.10.2")

    def test_get_ip_exception(self):
        dbapi = MagicMock()
        dbapi.network_get_by_type.side_effect = Exception("not found")
        with self.assertRaises(exception.SysinvException):
            self.op._get_floating_ip_by_net_type(
                dbapi, constants.NETWORK_TYPE_OAM)


class TestGetKubeIssuerUrl(unittest.TestCase):
    """Tests for _get_k8s_issuer_url."""

    def setUp(self):
        self.op = _create_operator()

    def test_get_issuer_url_found(self):
        dbapi = MagicMock()
        param = MagicMock()
        param.value = "https://10.10.10.2:30556/dex"
        dbapi.service_parameter_get_one.return_value = param
        result = self.op._get_k8s_issuer_url(dbapi)
        self.assertEqual(result, "https://10.10.10.2:30556/dex")

    def test_get_issuer_url_exception(self):
        dbapi = MagicMock()
        dbapi.service_parameter_get_one.side_effect = Exception("err")
        with self.assertRaises(exception.SysinvException):
            self.op._get_k8s_issuer_url(dbapi)


class TestHasHelmUserOverrides(unittest.TestCase):
    """Tests for _has_helm_user_overrides."""

    def setUp(self):
        self.op = _create_operator()

    def test_has_overrides_true(self):
        dbapi = MagicMock()
        override = MagicMock()
        override.user_overrides = "some: config"
        dbapi.helm_override_get.return_value = override
        result = self.op._has_helm_user_overrides(dbapi, "app-id", "dex")
        self.assertTrue(result)

    def test_has_overrides_empty(self):
        dbapi = MagicMock()
        override = MagicMock()
        override.user_overrides = None
        dbapi.helm_override_get.return_value = override
        result = self.op._has_helm_user_overrides(dbapi, "app-id", "dex")
        self.assertFalse(result)

    def test_has_overrides_exception(self):
        dbapi = MagicMock()
        dbapi.helm_override_get.side_effect = Exception("not found")
        with self.assertRaises(exception.SysinvException):
            self.op._has_helm_user_overrides(dbapi, "app-id", "dex")


class TestAppLifecycleActions(unittest.TestCase):
    """Tests for app_lifecycle_actions dispatch."""

    def setUp(self):
        self.op = _create_operator()
        self.ctx = MagicMock()
        self.conductor = MagicMock()
        self.app = MagicMock()
        self.app_op = MagicMock()

    def _hook(self, lc_type, timing, operation, mode=None):
        hook = MagicMock()
        hook.lifecycle_type = lc_type
        hook.relative_timing = timing
        hook.operation = operation
        hook.mode = mode
        return hook

    @patch.object(OidcAppLifecycleOperator, 'pre_apply_check')
    def test_semantic_check_pre_apply(self, mock_check):
        hook = self._hook(
            Lc.APP_LIFECYCLE_TYPE_SEMANTIC_CHECK,
            Lc.APP_LIFECYCLE_TIMING_PRE,
            constants.APP_APPLY_OP,
            mode='manual')
        self.op.app_lifecycle_actions(
            self.ctx, self.conductor, self.app_op, self.app, hook)
        mock_check.assert_called_once()

    @patch.object(OidcAppLifecycleOperator, 'pre_apply_check')
    @patch('os.path.isfile', return_value=True)
    def test_semantic_check_auto_bootstrap_raises(self, mock_isfile,
                                                   mock_check):
        hook = self._hook(
            Lc.APP_LIFECYCLE_TYPE_SEMANTIC_CHECK,
            Lc.APP_LIFECYCLE_TIMING_PRE,
            constants.APP_APPLY_OP,
            mode=Lc.APP_LIFECYCLE_MODE_AUTO)
        with self.assertRaises(
                exception.LifecycleSemanticCheckException):
            self.op.app_lifecycle_actions(
                self.ctx, self.conductor, self.app_op, self.app, hook)

    @patch.object(OidcAppLifecycleOperator, 'pre_apply_operation')
    def test_operation_pre_apply(self, mock_pre):
        hook = self._hook(
            Lc.APP_LIFECYCLE_TYPE_OPERATION,
            Lc.APP_LIFECYCLE_TIMING_PRE,
            constants.APP_APPLY_OP)
        self.op.app_lifecycle_actions(
            self.ctx, self.conductor, self.app_op, self.app, hook)
        mock_pre.assert_called_once()

    @patch.object(OidcAppLifecycleOperator, 'post_apply')
    @patch.object(OidcAppLifecycleOperator, 'post_apply_operation')
    def test_operation_post_apply(self, mock_post_op, mock_post):
        hook = self._hook(
            Lc.APP_LIFECYCLE_TYPE_OPERATION,
            Lc.APP_LIFECYCLE_TIMING_POST,
            constants.APP_APPLY_OP)
        self.op.app_lifecycle_actions(
            self.ctx, self.conductor, self.app_op, self.app, hook)
        mock_post_op.assert_called_once()
        mock_post.assert_called_once()


class TestPreApplyCheck(unittest.TestCase):
    """Tests for pre_apply_check."""

    def setUp(self):
        self.op = _create_operator()

    @patch('k8sapp_oidc.lifecycle.lifecycle_oidc.dbapi')
    @patch.object(OidcAppLifecycleOperator, '_load_kube_config')
    @patch.object(OidcAppLifecycleOperator,
                  '_is_oidc_overrides_fully_configured')
    def test_not_configured_not_subcloud(self, mock_conf, mock_kube,
                                         mock_dbapi):
        mock_conf.return_value = False
        mock_db = mock_dbapi.get_instance.return_value
        system = MagicMock()
        system.distributed_cloud_role = "controller"
        mock_db.isystem_get_one.return_value = system
        mock_db.service_parameter_get_one.side_effect = \
            Exception("not found")
        with self.assertRaises(exception.SysinvException):
            self.op.pre_apply_check(MagicMock(), MagicMock())

    @patch.object(OidcAppLifecycleOperator, '_validate_dex_tls_secret')
    @patch('k8sapp_oidc.lifecycle.lifecycle_oidc.dbapi')
    @patch.object(OidcAppLifecycleOperator, '_load_kube_config')
    @patch.object(OidcAppLifecycleOperator,
                  '_is_oidc_overrides_fully_configured')
    def test_configured_passes(self, mock_conf, mock_kube, mock_dbapi,
                               mock_validate):
        mock_conf.return_value = True
        self.op.pre_apply_check(MagicMock(), MagicMock())
        mock_validate.assert_called_once()


class TestPostApplyOperation(unittest.TestCase):
    """Tests for post_apply_operation."""

    def setUp(self):
        self.op = _create_operator()

    @patch('k8sapp_oidc.lifecycle.lifecycle_oidc.dbapi')
    @patch.object(OidcAppLifecycleOperator, '_dump_oidc_login_config')
    @patch.object(OidcAppLifecycleOperator, '_load_kube_config')
    def test_calls_dump(self, mock_kube, mock_dump, mock_dbapi):
        self.op.post_apply_operation(MagicMock(), MagicMock(), MagicMock())
        mock_dump.assert_called_once()


class TestDefaultOidcConfiguration(unittest.TestCase):
    """Tests for _default_oidc_configuration."""

    def setUp(self):
        self.op = _create_operator()

    @patch.object(OidcAppLifecycleOperator,
                  '_configure_secret_observer_override')
    @patch.object(OidcAppLifecycleOperator,
                  '_configure_dex_override')
    @patch.object(OidcAppLifecycleOperator,
                  '_configure_oidc_client_override')
    @patch.object(OidcAppLifecycleOperator, '_apply_oidc_certificate')
    @patch.object(OidcAppLifecycleOperator, '_get_ldap_password')
    @patch.object(OidcAppLifecycleOperator,
                  '_get_floating_ip_by_net_type')
    @patch.object(OidcAppLifecycleOperator,
                  '_extract_oam_ip_from_oidc_issuer_url')
    @patch.object(OidcAppLifecycleOperator, '_get_k8s_issuer_url')
    def test_configures_all(self, mock_issuer, mock_extract, mock_ip,
                            mock_ldap, mock_cert,
                            mock_oidc, mock_dex, mock_secret):
        mock_issuer.return_value = "https://10.10.10.2:30556/dex"
        mock_extract.return_value = "10.10.10.2"
        mock_ip.return_value = "192.168.204.2"
        mock_ldap.return_value = "pass"
        self.op._default_oidc_configuration(MagicMock())
        mock_cert.assert_called_once()
        mock_dex.assert_called_once()
        mock_oidc.assert_called_once()
        mock_secret.assert_called_once()


class TestIsOidcOverridesConfigured(unittest.TestCase):
    """Tests for _is_oidc_overrides_fully_configured."""

    def setUp(self):
        self.op = _create_operator()

    @patch.object(OidcAppLifecycleOperator, '_has_helm_user_overrides')
    def test_all_configured(self, mock_has):
        mock_has.return_value = True
        dbapi = MagicMock()
        app = MagicMock()
        app.id = "app-id"
        dbapi.kube_app_get_endswith.return_value = app
        result = self.op._is_oidc_overrides_fully_configured(dbapi)
        self.assertTrue(result)

    @patch.object(OidcAppLifecycleOperator, '_has_helm_user_overrides')
    def test_not_configured(self, mock_has):
        mock_has.return_value = False
        dbapi = MagicMock()
        app = MagicMock()
        app.id = "app-id"
        dbapi.kube_app_get_endswith.return_value = app
        result = self.op._is_oidc_overrides_fully_configured(dbapi)
        self.assertFalse(result)


class TestUpdateHelmUserOverrides(unittest.TestCase):
    """Tests for _update_helm_user_overrides."""

    def setUp(self):
        self.op = _create_operator()

    def test_creates_new_override(self):
        dbapi = MagicMock()
        db_app = MagicMock()
        db_app.id = "app-id"
        dbapi.kube_app_get.return_value = db_app
        dbapi.helm_override_get.side_effect = exception.NotFound()
        self.op._update_helm_user_overrides(
            dbapi, "oidc-auth", "dex", "kube-system", {"key": "val"})
        dbapi.helm_override_create.assert_called_once()

    def test_updates_existing_override(self):
        dbapi = MagicMock()
        db_app = MagicMock()
        db_app.id = "app-id"
        dbapi.kube_app_get.return_value = db_app
        dbapi.helm_override_get.return_value = MagicMock()
        self.op._update_helm_user_overrides(
            dbapi, "oidc-auth", "dex", "kube-system", {"key": "val"})
        dbapi.helm_override_update.assert_called_once()

    def test_app_not_found_raises(self):
        dbapi = MagicMock()
        dbapi.kube_app_get.side_effect = Exception("not found")
        with self.assertRaises(exception.SysinvException):
            self.op._update_helm_user_overrides(
                dbapi, "oidc-auth", "dex", "kube-system", {"k": "v"})


class TestConfigureOidcClientOverride(unittest.TestCase):
    """Tests for _configure_oidc_client_override."""

    def setUp(self):
        self.op = _create_operator()

    @patch.object(OidcAppLifecycleOperator, '_update_helm_user_overrides')
    def test_configures_override(self, mock_update):
        self.op._configure_oidc_client_override(MagicMock())
        mock_update.assert_called_once()

    @patch.object(OidcAppLifecycleOperator, '_update_helm_user_overrides')
    def test_exception_raises(self, mock_update):
        mock_update.side_effect = Exception("fail")
        with self.assertRaises(exception.SysinvException):
            self.op._configure_oidc_client_override(MagicMock())


class TestConfigureSecretObserverOverride(unittest.TestCase):
    """Tests for _configure_secret_observer_override."""

    def setUp(self):
        self.op = _create_operator()

    @patch.object(OidcAppLifecycleOperator, '_update_helm_user_overrides')
    def test_configures(self, mock_update):
        self.op._configure_secret_observer_override(MagicMock())
        mock_update.assert_called_once()


class TestConfigureDexOverride(unittest.TestCase):
    """Tests for _configure_dex_override."""

    def setUp(self):
        self.op = _create_operator()

    @patch.object(OidcAppLifecycleOperator, '_update_helm_user_overrides')
    @patch.object(OidcAppLifecycleOperator,
                  '_get_floating_ip_by_net_type')
    def test_configures(self, mock_ip, mock_update):
        mock_ip.return_value = "10.10.10.2"
        self.op._configure_dex_override(
            MagicMock(), "192.168.204.2", "ldappass")
        mock_update.assert_called_once()


class TestGetOidcClientId(unittest.TestCase):
    """Tests for _get_oidc_client_id."""

    def setUp(self):
        self.op = _create_operator()

    def test_returns_configured_id(self):
        dbapi = MagicMock()
        param = MagicMock()
        param.value = "my-client-id"
        dbapi.service_parameter_get_one.return_value = param
        result = self.op._get_oidc_client_id(dbapi)
        self.assertEqual(result, "my-client-id")

    def test_returns_default_on_not_found(self):
        from k8sapp_oidc.common import constants as app_constants
        dbapi = MagicMock()
        dbapi.service_parameter_get_one.side_effect = \
            exception.NotFound()
        result = self.op._get_oidc_client_id(dbapi)
        self.assertEqual(result, app_constants.DEFAULT_OIDC_CLIENT_ID)


class TestGetOidcClientSecret(unittest.TestCase):
    """Tests for _get_oidc_client_secret."""

    def setUp(self):
        self.op = _create_operator()

    def test_returns_secret_from_overrides(self):
        import yaml
        dbapi = MagicMock()
        db_app = MagicMock()
        db_app.id = "app-id"
        dbapi.kube_app_get.return_value = db_app
        override = MagicMock()
        override.user_overrides = yaml.safe_dump(
            {"config": {"client_secret": "my-secret"}})
        dbapi.helm_override_get.return_value = override
        result = self.op._get_oidc_client_secret(dbapi)
        self.assertEqual(result, "my-secret")

    def test_returns_default_on_missing(self):
        from k8sapp_oidc.common import constants as app_constants
        dbapi = MagicMock()
        db_app = MagicMock()
        db_app.id = "app-id"
        dbapi.kube_app_get.return_value = db_app
        override = MagicMock()
        override.user_overrides = None
        dbapi.helm_override_get.return_value = override
        result = self.op._get_oidc_client_secret(dbapi)
        self.assertEqual(result, app_constants.DEFAULT_OIDC_CLIENT_SECRET)


class TestGetLdapPassword(unittest.TestCase):
    """Tests for _get_ldap_password."""

    def setUp(self):
        self.op = _create_operator()

    @patch('k8sapp_oidc.lifecycle.lifecycle_oidc.keyring')
    def test_returns_password(self, mock_keyring):
        mock_keyring.get_password.return_value = "ldap-pass"
        result = self.op._get_ldap_password()
        self.assertEqual(result, "ldap-pass")

    @patch('k8sapp_oidc.lifecycle.lifecycle_oidc.keyring')
    def test_exception_raises(self, mock_keyring):
        mock_keyring.get_password.side_effect = Exception("err")
        with self.assertRaises(exception.SysinvException):
            self.op._get_ldap_password()


class TestApplyOidcCertificate(unittest.TestCase):
    """Tests for _apply_oidc_certificate."""

    def setUp(self):
        self.op = _create_operator()

    @patch('k8sapp_oidc.lifecycle.lifecycle_oidc.client')
    def test_creates_certificate(self, mock_k8s_client):
        mock_api = MagicMock()
        mock_k8s_client.CustomObjectsApi.return_value = mock_api
        mock_api.get_namespaced_custom_object.side_effect = \
            Exception("not found")
        self.op._apply_oidc_certificate("10.10.10.2")
        mock_api.create_namespaced_custom_object.assert_called_once()

    @patch('k8sapp_oidc.lifecycle.lifecycle_oidc.client')
    def test_replaces_existing_certificate(self, mock_k8s_client):
        mock_api = MagicMock()
        mock_k8s_client.CustomObjectsApi.return_value = mock_api
        mock_api.get_namespaced_custom_object.return_value = {}
        self.op._apply_oidc_certificate("10.10.10.2")
        mock_api.delete_namespaced_custom_object.assert_called_once()
        mock_api.create_namespaced_custom_object.assert_called_once()


class TestPostApply(unittest.TestCase):
    """Tests for post_apply."""

    def setUp(self):
        self.op = _create_operator()

    @patch('k8sapp_oidc.lifecycle.lifecycle_oidc.os.path.isfile')
    @patch('k8sapp_oidc.lifecycle.lifecycle_oidc.dbapi')
    def test_post_apply_triggers_keystone(self, mock_dbapi, mock_isfile):
        # First isfile (INITIAL_CONFIG_COMPLETE_FLAG) -> True so the
        # deferral branch is skipped; second isfile (federation marker)
        # -> False so the trigger is not short-circuited.
        mock_isfile.side_effect = [True, False]
        mock_db = mock_dbapi.get_instance.return_value
        mock_db.service_parameter_get_one.return_value = MagicMock()
        conductor = MagicMock()
        self.op.post_apply(MagicMock(), conductor)
        conductor._config_update_hosts.assert_called_once()
        conductor._config_apply_runtime_manifest.assert_called_once()

    @patch('k8sapp_oidc.lifecycle.lifecycle_oidc.os.path.isfile')
    @patch('k8sapp_oidc.lifecycle.lifecycle_oidc.dbapi')
    def test_post_apply_skips_when_no_issuer(self, mock_dbapi, mock_isfile):
        mock_isfile.side_effect = [True, False]
        mock_db = mock_dbapi.get_instance.return_value
        mock_db.service_parameter_get_one.side_effect = \
            exception.NotFound()
        conductor = MagicMock()
        self.op.post_apply(MagicMock(), conductor)
        conductor._config_update_hosts.assert_not_called()


# ============================================================
# Additional tests to raise coverage of lifecycle_oidc.py
# ============================================================


class TestGetFloatingIpByNetType(unittest.TestCase):
    """Tests for _get_floating_ip_by_net_type."""

    def setUp(self):
        self.op = _create_operator()

    def test_returns_floating_ip(self):
        dbapi = MagicMock()
        net = MagicMock()
        net.pool_uuid = "pool-uuid"
        dbapi.network_get_by_type.return_value = net
        pool = MagicMock()
        pool.floating_address = "10.10.10.2"
        dbapi.address_pool_get.return_value = pool
        result = self.op._get_floating_ip_by_net_type(
            dbapi, constants.NETWORK_TYPE_OAM)
        self.assertEqual(result, "10.10.10.2")

    def test_exception_raises(self):
        dbapi = MagicMock()
        dbapi.network_get_by_type.side_effect = Exception("no net")
        with self.assertRaises(exception.SysinvException):
            self.op._get_floating_ip_by_net_type(
                dbapi, constants.NETWORK_TYPE_OAM)


class TestGetLdapPasswordExtra(unittest.TestCase):
    """Tests for _get_ldap_password."""

    def setUp(self):
        self.op = _create_operator()

    @patch('k8sapp_oidc.lifecycle.lifecycle_oidc.keyring')
    def test_returns_password(self, mock_keyring):
        mock_keyring.get_password.return_value = "secret"
        result = self.op._get_ldap_password()
        self.assertEqual(result, "secret")

    @patch('k8sapp_oidc.lifecycle.lifecycle_oidc.keyring')
    def test_empty_password_raises(self, mock_keyring):
        mock_keyring.get_password.return_value = None
        with self.assertRaises(exception.SysinvException):
            self.op._get_ldap_password()

    @patch('k8sapp_oidc.lifecycle.lifecycle_oidc.keyring')
    def test_keyring_exception_raises(self, mock_keyring):
        mock_keyring.get_password.side_effect = Exception("keyring down")
        with self.assertRaises(exception.SysinvException):
            self.op._get_ldap_password()


class TestConfigureOidcClientOverrideBody(unittest.TestCase):
    """Tests for _configure_oidc_client_override values."""

    def setUp(self):
        self.op = _create_operator()

    @patch.object(OidcAppLifecycleOperator, '_update_helm_user_overrides')
    def test_values_passed(self, mock_update):
        self.op._configure_oidc_client_override(MagicMock())
        _, kwargs = mock_update.call_args
        self.assertIn('values_dict', kwargs)
        self.assertEqual(
            kwargs['values_dict']['tlsName'],
            "oidc-auth-apps-certificate")

    @patch.object(OidcAppLifecycleOperator, '_update_helm_user_overrides')
    def test_update_failure_raises(self, mock_update):
        mock_update.side_effect = Exception("fail")
        with self.assertRaises(exception.SysinvException):
            self.op._configure_oidc_client_override(MagicMock())


class TestConfigureDexOverrideBody(unittest.TestCase):
    """Tests for _configure_dex_override values."""

    def setUp(self):
        self.op = _create_operator()

    @patch.object(OidcAppLifecycleOperator, '_update_helm_user_overrides')
    def test_ipv4_host(self, mock_update):
        self.op._configure_dex_override(
            MagicMock(), "192.168.204.2", "ldappass")
        mock_update.assert_called_once()

    @patch.object(OidcAppLifecycleOperator, '_update_helm_user_overrides')
    def test_ipv6_host_bracketed(self, mock_update):
        self.op._configure_dex_override(
            MagicMock(), "fd01::2", "ldappass")
        mock_update.assert_called_once()


class TestStripTlsFromUserOverrides(unittest.TestCase):
    """Tests for _strip_tls_from_user_overrides and helpers."""

    def setUp(self):
        self.op = _create_operator()

    def test_app_not_found_returns(self):
        dbapi = MagicMock()
        dbapi.kube_app_get.side_effect = Exception("not found")
        # Returns without raising when the app is not found.
        self.op._strip_tls_from_user_overrides(dbapi)

    @patch.object(OidcAppLifecycleOperator, '_strip_tls_keys_from_dex')
    @patch.object(OidcAppLifecycleOperator, '_strip_tls_keys_from_chart')
    def test_strips_both_charts(self, mock_chart, mock_dex):
        dbapi = MagicMock()
        db_app = MagicMock()
        db_app.id = 1
        dbapi.kube_app_get.return_value = db_app
        self.op._strip_tls_from_user_overrides(dbapi)
        mock_chart.assert_called_once()
        mock_dex.assert_called_once()


class TestStripTlsKeysFromChart(unittest.TestCase):
    """Tests for _strip_tls_keys_from_chart."""

    def setUp(self):
        self.op = _create_operator()

    def test_no_overrides_returns(self):
        dbapi = MagicMock()
        ho = MagicMock()
        ho.user_overrides = None
        dbapi.helm_override_get.return_value = ho
        self.op._strip_tls_keys_from_chart(
            dbapi, 1, "oidc-client", ['tlsMinVersion'])
        dbapi.helm_override_update.assert_not_called()

    def test_strips_and_updates(self):
        dbapi = MagicMock()
        ho = MagicMock()
        ho.user_overrides = (
            "config:\n  tlsMinVersion: VersionTLS12\n  other: keep\n")
        dbapi.helm_override_get.return_value = ho
        self.op._strip_tls_keys_from_chart(
            dbapi, 1, "oidc-client", ['tlsMinVersion'])
        dbapi.helm_override_update.assert_called_once()

    def test_no_matching_key_no_update(self):
        dbapi = MagicMock()
        ho = MagicMock()
        ho.user_overrides = "config:\n  other: keep\n"
        dbapi.helm_override_get.return_value = ho
        self.op._strip_tls_keys_from_chart(
            dbapi, 1, "oidc-client", ['tlsMinVersion'])
        dbapi.helm_override_update.assert_not_called()

    def test_not_found_swallowed(self):
        dbapi = MagicMock()
        dbapi.helm_override_get.side_effect = exception.NotFound()
        # NotFound is swallowed, so no exception is raised.
        self.op._strip_tls_keys_from_chart(
            dbapi, 1, "oidc-client", ['tlsMinVersion'])


class TestStripTlsKeysFromDex(unittest.TestCase):
    """Tests for _strip_tls_keys_from_dex."""

    def setUp(self):
        self.op = _create_operator()

    def test_strips_web_tls(self):
        dbapi = MagicMock()
        ho = MagicMock()
        ho.user_overrides = (
            "config:\n  web:\n    tlsMinVersion: VersionTLS12\n")
        dbapi.helm_override_get.return_value = ho
        self.op._strip_tls_keys_from_dex(dbapi, 1)
        dbapi.helm_override_update.assert_called_once()

    def test_no_overrides_returns(self):
        dbapi = MagicMock()
        ho = MagicMock()
        ho.user_overrides = None
        dbapi.helm_override_get.return_value = ho
        self.op._strip_tls_keys_from_dex(dbapi, 1)
        dbapi.helm_override_update.assert_not_called()


class TestGetDexTlsSecretName(unittest.TestCase):
    """Tests for _get_dex_tls_secret_name."""

    def setUp(self):
        self.op = _create_operator()

    def _dbapi_with_overrides(self, overrides_yaml):
        dbapi = MagicMock()
        db_app = MagicMock()
        db_app.id = 1
        dbapi.kube_app_get.return_value = db_app
        ho = MagicMock()
        ho.user_overrides = overrides_yaml
        dbapi.helm_override_get.return_value = ho
        return dbapi

    def test_resolves_secret_name(self):
        overrides = (
            "volumeMounts:\n"
            "  - name: dex-tls\n"
            "    mountPath: /etc/dex/tls\n"
            "volumes:\n"
            "  - name: dex-tls\n"
            "    secret:\n"
            "      secretName: dex-tls-secret\n"
        )
        dbapi = self._dbapi_with_overrides(overrides)
        result = self.op._get_dex_tls_secret_name(dbapi)
        self.assertEqual(result, "dex-tls-secret")

    def test_no_overrides_raises(self):
        dbapi = self._dbapi_with_overrides(None)
        with self.assertRaises(exception.SysinvException):
            self.op._get_dex_tls_secret_name(dbapi)

    def test_no_matching_mount_raises(self):
        overrides = (
            "volumeMounts:\n"
            "  - name: other\n"
            "    mountPath: /etc/other\n"
        )
        dbapi = self._dbapi_with_overrides(overrides)
        with self.assertRaises(exception.SysinvException):
            self.op._get_dex_tls_secret_name(dbapi)


class TestValidateDexTlsSecret(unittest.TestCase):
    """Tests for _validate_dex_tls_secret."""

    def setUp(self):
        self.op = _create_operator()

    @patch('k8sapp_oidc.lifecycle.lifecycle_oidc.client')
    @patch.object(OidcAppLifecycleOperator, '_get_dex_tls_secret_name')
    def test_valid_secret_passes(self, mock_name, mock_client):
        mock_name.return_value = "dex-tls-secret"
        secret = MagicMock()
        secret.data = {'ca.crt': 'a', 'tls.crt': 'b', 'tls.key': 'c'}
        mock_client.CoreV1Api.return_value.read_namespaced_secret\
            .return_value = secret
        # A valid secret passes validation without raising.
        self.op._validate_dex_tls_secret(MagicMock())

    @patch('k8sapp_oidc.lifecycle.lifecycle_oidc.client')
    @patch.object(OidcAppLifecycleOperator, '_get_dex_tls_secret_name')
    def test_missing_fields_raises(self, mock_name, mock_client):
        mock_name.return_value = "dex-tls-secret"
        secret = MagicMock()
        secret.data = {'ca.crt': 'a'}
        mock_client.CoreV1Api.return_value.read_namespaced_secret\
            .return_value = secret
        with self.assertRaises(exception.SysinvException):
            self.op._validate_dex_tls_secret(MagicMock())

    @patch('k8sapp_oidc.lifecycle.lifecycle_oidc.client')
    @patch.object(OidcAppLifecycleOperator, '_get_dex_tls_secret_name')
    def test_read_failure_raises(self, mock_name, mock_client):
        mock_name.return_value = "dex-tls-secret"
        mock_client.CoreV1Api.return_value.read_namespaced_secret\
            .side_effect = Exception("api error")
        with self.assertRaises(exception.SysinvException):
            self.op._validate_dex_tls_secret(MagicMock())


class TestDumpOidcLoginConfig(unittest.TestCase):
    """Tests for _dump_oidc_login_config."""

    def setUp(self):
        self.op = _create_operator()

    @patch.object(OidcAppLifecycleOperator, '_get_issuer_ca_cert')
    @patch.object(OidcAppLifecycleOperator, '_get_oidc_client_secret')
    @patch.object(OidcAppLifecycleOperator, '_get_oidc_client_id')
    @patch.object(OidcAppLifecycleOperator, '_get_k8s_issuer_url')
    def test_missing_param_raises(self, mock_url, mock_id,
                                  mock_secret, mock_ca):
        mock_url.return_value = "https://10.10.10.2:30556/dex"
        mock_id.return_value = None
        mock_secret.return_value = "s"
        mock_ca.return_value = "ca"
        with self.assertRaises(exception.SysinvException):
            self.op._dump_oidc_login_config(MagicMock())


class TestGetIssuerCaCert(unittest.TestCase):
    """Tests for _get_issuer_ca_cert."""

    def setUp(self):
        self.op = _create_operator()

    @patch('k8sapp_oidc.lifecycle.lifecycle_oidc.dbapi')
    @patch('k8sapp_oidc.lifecycle.lifecycle_oidc.client')
    @patch.object(OidcAppLifecycleOperator, '_get_dex_tls_secret_name')
    def test_returns_ca(self, mock_name, mock_client, mock_dbapi):
        mock_name.return_value = "dex-tls-secret"
        secret = MagicMock()
        secret.data = {'ca.crt': 'base64ca'}
        mock_client.CoreV1Api.return_value.read_namespaced_secret\
            .return_value = secret
        result = self.op._get_issuer_ca_cert()
        self.assertEqual(result, 'base64ca')

    @patch('k8sapp_oidc.lifecycle.lifecycle_oidc.dbapi')
    @patch('k8sapp_oidc.lifecycle.lifecycle_oidc.client')
    @patch.object(OidcAppLifecycleOperator, '_get_dex_tls_secret_name')
    def test_no_ca_raises(self, mock_name, mock_client, mock_dbapi):
        mock_name.return_value = "dex-tls-secret"
        secret = MagicMock()
        secret.data = {}
        mock_client.CoreV1Api.return_value.read_namespaced_secret\
            .return_value = secret
        with self.assertRaises(exception.SysinvException):
            self.op._get_issuer_ca_cert()


class TestPreApplyOperation(unittest.TestCase):
    """Tests for pre_apply_operation."""

    def setUp(self):
        self.op = _create_operator()

    @patch('k8sapp_oidc.lifecycle.lifecycle_oidc.dbapi')
    @patch.object(OidcAppLifecycleOperator, '_strip_tls_from_user_overrides')
    @patch.object(OidcAppLifecycleOperator, '_load_kube_config')
    @patch.object(OidcAppLifecycleOperator,
                  '_is_oidc_overrides_fully_configured')
    def test_configured_returns_early(self, mock_conf, mock_kube,
                                       mock_strip, mock_dbapi):
        mock_conf.return_value = True
        self.op.pre_apply_operation(MagicMock(), MagicMock(), MagicMock())
        mock_strip.assert_called_once()

    @patch('k8sapp_oidc.lifecycle.lifecycle_oidc.dbapi')
    @patch.object(OidcAppLifecycleOperator, '_default_oidc_configuration')
    @patch.object(OidcAppLifecycleOperator, '_strip_tls_from_user_overrides')
    @patch.object(OidcAppLifecycleOperator, '_load_kube_config')
    @patch.object(OidcAppLifecycleOperator,
                  '_is_oidc_overrides_fully_configured')
    def test_not_configured_applies_default(self, mock_conf, mock_kube,
                                            mock_strip, mock_default,
                                            mock_dbapi):
        mock_conf.return_value = False
        self.op.pre_apply_operation(MagicMock(), MagicMock(), MagicMock())
        mock_default.assert_called_once()


class TestPostApplyOperationExtra(unittest.TestCase):
    """Tests for post_apply_operation."""

    def setUp(self):
        self.op = _create_operator()

    @patch('k8sapp_oidc.lifecycle.lifecycle_oidc.dbapi')
    @patch.object(OidcAppLifecycleOperator, '_dump_oidc_login_config')
    @patch.object(OidcAppLifecycleOperator, '_load_kube_config')
    def test_dumps_config(self, mock_kube, mock_dump, mock_dbapi):
        self.op.post_apply_operation(
            MagicMock(), MagicMock(), MagicMock())
        mock_dump.assert_called_once()


class TestPostApplyDeferral(unittest.TestCase):
    """Tests for post_apply deferral branch."""

    def setUp(self):
        self.op = _create_operator()

    @patch('k8sapp_oidc.lifecycle.lifecycle_oidc.open',
           new_callable=MagicMock)
    @patch('k8sapp_oidc.lifecycle.lifecycle_oidc.os.path.isfile')
    def test_defers_when_initial_config_incomplete(self, mock_isfile,
                                                    mock_open):
        # INITIAL_CONFIG_COMPLETE_FLAG missing -> defer, create flag file
        mock_isfile.return_value = False
        conductor = MagicMock()
        self.op.post_apply(MagicMock(), conductor)
        conductor._config_update_hosts.assert_not_called()


class TestDumpOidcLoginConfigExtra(unittest.TestCase):
    """More tests for _dump_oidc_login_config."""

    def setUp(self):
        self.op = _create_operator()

    @patch('k8sapp_oidc.lifecycle.lifecycle_oidc.os.rename')
    @patch('k8sapp_oidc.lifecycle.lifecycle_oidc.os.chmod')
    @patch('k8sapp_oidc.lifecycle.lifecycle_oidc.open',
           new_callable=MagicMock)
    @patch.object(OidcAppLifecycleOperator, '_get_issuer_ca_cert')
    @patch.object(OidcAppLifecycleOperator, '_get_oidc_client_secret')
    @patch.object(OidcAppLifecycleOperator, '_get_oidc_client_id')
    @patch.object(OidcAppLifecycleOperator, '_get_k8s_issuer_url')
    def test_writes_config(self, mock_url, mock_id, mock_secret,
                           mock_ca, mock_open_fn, mock_chmod,
                           mock_rename):
        mock_url.return_value = "https://10.10.10.2:30556/dex"
        mock_id.return_value = "stx-oidc-client-app"
        mock_secret.return_value = "sec"
        mock_ca.return_value = "ca-data"
        self.op._dump_oidc_login_config(MagicMock())
        mock_rename.assert_called_once()

    @patch('k8sapp_oidc.lifecycle.lifecycle_oidc.os.unlink')
    @patch('k8sapp_oidc.lifecycle.lifecycle_oidc.open',
           side_effect=Exception("disk full"))
    @patch.object(OidcAppLifecycleOperator, '_get_issuer_ca_cert')
    @patch.object(OidcAppLifecycleOperator, '_get_oidc_client_secret')
    @patch.object(OidcAppLifecycleOperator, '_get_oidc_client_id')
    @patch.object(OidcAppLifecycleOperator, '_get_k8s_issuer_url')
    def test_write_failure_raises(self, mock_url, mock_id, mock_secret,
                                  mock_ca, mock_open_fn, mock_unlink):
        mock_url.return_value = "https://10.10.10.2:30556/dex"
        mock_id.return_value = "id"
        mock_secret.return_value = "sec"
        mock_ca.return_value = "ca"
        with self.assertRaises(exception.SysinvException):
            self.op._dump_oidc_login_config(MagicMock())


class TestPreApplyCheckBranches(unittest.TestCase):
    """Cover pre_apply_check subcloud and non-subcloud branches."""

    def setUp(self):
        self.op = _create_operator()

    @patch('k8sapp_oidc.lifecycle.lifecycle_oidc.dbapi')
    @patch.object(OidcAppLifecycleOperator, '_is_subcloud')
    @patch.object(OidcAppLifecycleOperator, '_load_kube_config')
    @patch.object(OidcAppLifecycleOperator,
                  '_is_oidc_overrides_fully_configured')
    def test_subcloud_not_configured_raises(self, mock_conf, mock_kube,
                                            mock_subcloud, mock_dbapi):
        mock_conf.return_value = False
        mock_subcloud.return_value = True
        with self.assertRaises(exception.SysinvException):
            self.op.pre_apply_check(MagicMock(), MagicMock())

    @patch('k8sapp_oidc.lifecycle.lifecycle_oidc.dbapi')
    @patch.object(OidcAppLifecycleOperator,
                  '_extract_oam_ip_from_oidc_issuer_url')
    @patch.object(OidcAppLifecycleOperator, '_get_k8s_issuer_url')
    @patch.object(OidcAppLifecycleOperator, '_is_subcloud')
    @patch.object(OidcAppLifecycleOperator, '_load_kube_config')
    @patch.object(OidcAppLifecycleOperator,
                  '_is_oidc_overrides_fully_configured')
    def test_non_subcloud_validates_issuer(self, mock_conf, mock_kube,
                                           mock_subcloud, mock_issuer,
                                           mock_extract, mock_dbapi):
        mock_conf.return_value = False
        mock_subcloud.return_value = False
        mock_issuer.return_value = "https://10.10.10.2:30556/dex"
        self.op.pre_apply_check(MagicMock(), MagicMock())
        mock_extract.assert_called_once()
