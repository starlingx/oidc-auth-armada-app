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

    @patch('k8sapp_oidc.lifecycle.lifecycle_oidc.dbapi')
    @patch.object(OidcAppLifecycleOperator, '_load_kube_config')
    @patch.object(OidcAppLifecycleOperator,
                  '_is_oidc_overrides_fully_configured')
    def test_configured_passes(self, mock_conf, mock_kube, mock_dbapi):
        mock_conf.return_value = True
        self.op.pre_apply_check(MagicMock(), MagicMock())


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
    @patch.object(OidcAppLifecycleOperator, '_get_platform_tls_config')
    @patch.object(OidcAppLifecycleOperator, '_apply_oidc_certificate')
    @patch.object(OidcAppLifecycleOperator, '_get_ldap_password')
    @patch.object(OidcAppLifecycleOperator,
                  '_get_floating_ip_by_net_type')
    @patch.object(OidcAppLifecycleOperator,
                  '_extract_oam_ip_from_oidc_issuer_url')
    @patch.object(OidcAppLifecycleOperator, '_get_k8s_issuer_url')
    def test_configures_all(self, mock_issuer, mock_extract, mock_ip,
                            mock_ldap, mock_cert, mock_tls,
                            mock_oidc, mock_dex, mock_secret):
        mock_issuer.return_value = "https://10.10.10.2:30556/dex"
        mock_extract.return_value = "10.10.10.2"
        mock_ip.return_value = "192.168.204.2"
        mock_ldap.return_value = "pass"
        mock_tls.return_value = ("TLSv1.2", "HIGH")
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
        self.op._configure_oidc_client_override(
            MagicMock(), "TLSv1.2", "HIGH")
        mock_update.assert_called_once()

    @patch.object(OidcAppLifecycleOperator, '_update_helm_user_overrides')
    def test_exception_raises(self, mock_update):
        mock_update.side_effect = Exception("fail")
        with self.assertRaises(exception.SysinvException):
            self.op._configure_oidc_client_override(
                MagicMock(), "TLSv1.2", "HIGH")


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
            MagicMock(), "192.168.204.2", "ldappass", "TLSv1.2")
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

    @patch('k8sapp_oidc.lifecycle.lifecycle_oidc.dbapi')
    def test_post_apply_triggers_keystone(self, mock_dbapi):
        mock_db = mock_dbapi.get_instance.return_value
        mock_db.service_parameter_get_one.return_value = MagicMock()
        conductor = MagicMock()
        self.op.post_apply(MagicMock(), conductor)
        conductor._config_update_hosts.assert_called_once()
        conductor._config_apply_runtime_manifest.assert_called_once()

    @patch('k8sapp_oidc.lifecycle.lifecycle_oidc.dbapi')
    def test_post_apply_skips_when_no_issuer(self, mock_dbapi):
        mock_db = mock_dbapi.get_instance.return_value
        mock_db.service_parameter_get_one.side_effect = \
            exception.NotFound()
        conductor = MagicMock()
        self.op.post_apply(MagicMock(), conductor)
        conductor._config_update_hosts.assert_not_called()
