#
# Copyright (c) 2024-2026 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#
# All Rights Reserved.
#

""" System inventory App lifecycle operator."""

import keyring
import os
import yaml

from netaddr import IPAddress
from oslo_log import log as logging
from urllib.parse import urlparse

from kubernetes import client
from kubernetes import config
from kubernetes.client.rest import ApiException

from k8sapp_oidc.common import constants as app_constants
from k8sapp_oidc.helm.dex_base import DEX_TLS_VERSION_MAP
from k8sapp_oidc.helm.dex_base import get_platform_tls_config

from sysinv.common import constants
from sysinv.common import exception
from sysinv.common import kubernetes as kube_utils
from sysinv.db import api as dbapi
from sysinv.helm import common
from sysinv.helm import lifecycle_base as base
from sysinv.helm.lifecycle_constants import LifecycleConstants as Lc


LOG = logging.getLogger(__name__)

DEFAULT_ISSUER_PORT = "30556"

CERTIFICATE_GROUP = "cert-manager.io"
CERTIFICATE_VERSION = "v1"
CERTIFICATE_NAMESPACE = common.HELM_NS_KUBE_SYSTEM
CERTIFICATE_PLURAL = "certificates"
CERTIFICATE_NAME = "oidc-auth-apps-certificate"


class OidcAppLifecycleOperator(base.AppLifecycleOperator):
    def app_lifecycle_actions(self, context, conductor_obj, app_op, app,
                              hook_info):

        """Perform lifecycle actions for an operation"""

        if (
            hook_info.lifecycle_type == Lc.APP_LIFECYCLE_TYPE_SEMANTIC_CHECK
            and hook_info.relative_timing == Lc.APP_LIFECYCLE_TIMING_PRE
            and hook_info.operation == constants.APP_APPLY_OP
        ):
            # Apply is controlled by ansible-playbooks during bootstrap
            if (
                os.path.isfile(constants.ANSIBLE_BOOTSTRAP_FLAG)
                and hook_info.mode == Lc.APP_LIFECYCLE_MODE_AUTO
            ):
                raise exception.LifecycleSemanticCheckException(
                    "Auto-apply disabled during bootstrap"
                )

            return self.pre_apply_check(context, conductor_obj)

        if (
            hook_info.lifecycle_type == Lc.APP_LIFECYCLE_TYPE_OPERATION
            and hook_info.relative_timing == Lc.APP_LIFECYCLE_TIMING_PRE
            and hook_info.operation == constants.APP_APPLY_OP
        ):
            return self.pre_apply_operation(context, conductor_obj, app)

        if (
            hook_info.lifecycle_type == Lc.APP_LIFECYCLE_TYPE_OPERATION
            and hook_info.relative_timing == Lc.APP_LIFECYCLE_TIMING_POST
            and hook_info.operation == constants.APP_APPLY_OP
        ):
            self.post_apply_operation(context, conductor_obj, app)
            self.post_apply(context, conductor_obj)
            return

        super(OidcAppLifecycleOperator, self).app_lifecycle_actions(
            context, conductor_obj, app_op, app, hook_info)

    def pre_apply_check(self, context, conductor_obj):
        """
        Pre-apply validation hook for the OIDC application resource.

        Validates whether a complete and usable OIDC configuration is
        available locally before the application is applied.

        Behavior:
        - Returns immediately if all required OIDC Helm overrides
          are present.
        - On subclouds with incomplete configuration, blocks the
          apply assuming OIDC is provided externally.
        - On non-subcloud systems, validates the configured OIDC
          issuer URL and extracts the OAM floating IP.

        If validation fails, the application transitions to the
        *apply-failed* state and the raised exception message is
        reported as the failure reason.

        :param context: Request context provided by the conductor.
        :param conductor_obj: Sysinv conductor manager instance.

        :raises SysinvException: If required OIDC configuration
          is missing or invalid.
        """
        # Load Kubernetes and Sysinv APIs
        self._load_kube_config()
        dbapi_instance = dbapi.get_instance()

        # Fully configured locally, apply it
        if self._is_oidc_overrides_fully_configured(dbapi_instance):
            return

        # Do not apply OIDC locally on subclouds if not fully configured,
        # assume it is using the OIDC app from somewhere else
        if self._is_subcloud(dbapi_instance):
            raise exception.SysinvException("Configuration not found")

        # Issuer URL must be pre-configured for the default
        # configuration can be applied. The methods bellow
        # will throw and stop the apply process if invalid
        issuer_url = self._get_k8s_issuer_url(dbapi_instance)
        self._extract_oam_ip_from_oidc_issuer_url(issuer_url)

    def post_apply_operation(self, context, conductor_obj, app):
        """
        Post-apply execution hook for the OIDC application operation.

        Dumps OIDC login parameters (issuer URL, client ID, client secret,
        issuer CA) to a well-known file so that kubeconfig-setup can read
        them to configure oidc-login exec blocks without user interaction.

        :param context: Request context provided by the conductor.
        :param conductor_obj: Sysinv conductor manager instance.
        :param app: Application object.
        """
        self._load_kube_config()
        dbapi_instance = dbapi.get_instance()
        self._dump_oidc_login_config(dbapi_instance)

    def pre_apply_operation(self, context, conductor_obj, app):
        """
        Pre-apply execution hook for the OIDC application operation.

        This hook runs immediately before the OIDC application is applied and
        ensures that a valid OIDC configuration exists.

        Behavior:
        - If all required OIDC Helm overrides are already present locally, the
          method performs no changes and allows the apply to proceed.
        - If the configuration is incomplete, a default OIDC configuration is
          generated and persisted, making the application ready to be applied.

        :param context: Request context provided by the conductor.
        :param conductor_obj: Sysinv conductor manager instance.
        """
        # Load Kubernetes and Sysinv APIs
        self._load_kube_config()
        dbapi_instance = dbapi.get_instance()

        self._sync_oidc_client_with_bootstrap_state(app.id, dbapi_instance)

        if self._is_oidc_overrides_fully_configured(dbapi_instance):
            # Fully configured locally, apply it
            LOG.info("OIDC ready to be applied")
            return

        # Apply default configuration
        self._default_oidc_configuration(dbapi_instance)
        LOG.info("OIDC configured and ready to be applied")

    def post_apply(self, context, conductor_obj):
        """Trigger Keystone federation setup after oidc-auth-apps is applied.

        After oidc-auth-apps is successfully deployed, this hook checks
        whether oidc-issuer-url is configured as a Kubernetes service
        parameter. If present, it triggers the keystone server runtime
        puppet manifest which includes the federation class, creating the
        IdP, mapping, and protocol resources in Keystone.

        If oidc-issuer-url is not configured (e.g., user provided custom
        Helm overrides pointing to an external OIDC provider), the puppet
        trigger is skipped to avoid contradictory state.

        :param context: Request context provided by the conductor.
        :param conductor_obj: Sysinv conductor manager instance.
        """
        dbapi_instance = dbapi.get_instance()

        try:
            dbapi_instance.service_parameter_get_one(
                constants.SERVICE_TYPE_KUBERNETES,
                constants.SERVICE_PARAM_SECTION_KUBERNETES_APISERVER,
                constants.SERVICE_PARAM_NAME_OIDC_ISSUER_URL,
            )
        except exception.NotFound:
            LOG.info("oidc-issuer-url not configured, skipping "
                     "Keystone federation trigger")
            return

        config_dict = {
            "personalities": [constants.CONTROLLER],
            "classes": ['openstack::keystone::server::runtime']
        }
        config_uuid = conductor_obj._config_update_hosts(
            context, config_dict['personalities']
        )
        conductor_obj._config_apply_runtime_manifest(
            context, config_uuid, config_dict
        )
        LOG.info("Triggered Keystone federation configuration "
                 "after oidc-auth-apps apply")

    def _sync_oidc_client_with_bootstrap_state(self, app_id, dbapi_instance):
        """
        Ensure the OIDC client chart is enabled or disabled according to the current bootstrap
        state of the system.

        In distributed deployments, the floating IP is only assigned after the OIDC client has
        already started. This can cause the client to be initialized with an invalid network
        configuration.
        To avoid this, the OIDC client chart is being disabled during bootstrap and re-enabled
        after controller-1 unlock completes.
        """

        # Skip for simplex systems (no floating IP timing issue)
        system_mode = dbapi_instance.isystem_get_one().system_mode
        if system_mode == constants.SYSTEM_MODE_SIMPLEX:
            return

        chart_name = app_constants.HELM_CHART_OIDC_CLIENT
        namespace = common.HELM_NS_KUBE_SYSTEM
        enable_key = common.HELM_CHART_ATTR_ENABLED
        system_overrides = dbapi_instance.helm_override_get(
            app_id,
            chart_name,
            namespace
        ).system_overrides

        current_enabled = system_overrides.get(enable_key, True)
        in_bootstrap = os.path.isfile(constants.ANSIBLE_BOOTSTRAP_FLAG)
        desired_enabled = not in_bootstrap

        # No update needed if state is already correct
        if current_enabled == desired_enabled:
            return

        system_overrides[enable_key] = desired_enabled
        dbapi_instance.helm_override_update(
            app_id,
            chart_name,
            namespace,
            {'system_overrides': system_overrides}
        )

    def _get_k8s_issuer_url(self, dbapi_instance):
        try:
            issuer_url = dbapi_instance.service_parameter_get_one(
                constants.SERVICE_TYPE_KUBERNETES,
                constants.SERVICE_PARAM_SECTION_KUBERNETES_APISERVER,
                constants.SERVICE_PARAM_NAME_OIDC_ISSUER_URL,
            )
            return issuer_url.value

        except exception.NotFound:
            raise exception.SysinvException(
                "Cannot apply default OIDC without issuer URL configured"
            )

        except Exception as e:
            raise exception.SysinvException(
                "Unexpected error trying to read Kubernetes parameters"
            ) from e

    def _is_oidc_overrides_fully_configured(self, dbapi_instance):
        """Check whether all required OIDC Helm chart user overrides are configured.

        This function verifies the presence of user overrides for the
        OIDC-related Helm charts (`oidc-client`, `dex`, and `secret-observer`)
        in the Sysinv database. These overrides are required for the correct
        configuration of the OIDC authentication stack.

        The configuration state is evaluated as follows:
        - Returns `True` if all required charts have populated user overrides.
        - Returns `False` if none of the required charts have user overrides.
        - Raises an exception if only a subset of the required overrides exists.

        :param sysinv.db.api.DbApi dbapi_instance: Sysinv database API instance
            used to query Helm application data.

        :returns bool: `True` if all required OIDC Helm chart user overrides exist
            and are populated, otherwise `False`.

        :raises SysinvException: If the OIDC overrides are partially configured
            or if an unexpected error occurs while accessing Helm application or
            override data.
        """
        db_app = dbapi_instance.kube_app_get(constants.HELM_APP_OIDC_AUTH)

        checks = (
            self._has_helm_user_overrides(
                dbapi_instance,
                db_app.id,
                app_constants.HELM_CHART_OIDC_CLIENT,
            ),
            self._has_helm_user_overrides(
                dbapi_instance,
                db_app.id,
                app_constants.HELM_CHART_DEX,
            ),
            self._has_helm_user_overrides(
                dbapi_instance,
                db_app.id,
                app_constants.HELM_CHART_SECRET_OBSERVER,
            ),
        )

        if all(checks):
            return True

        if not any(checks):
            return False

        raise exception.SysinvException("OIDC configuration is incomplete")

    def _has_helm_user_overrides(self, dbapi_instance, db_app_id, chart_name):
        """Check whether a Helm chart has user overrides configured.

        This function verifies that a specific Helm chart associated with the
        given application has a Helm override entry with non-empty user
        overrides stored in the Sysinv database.

        :param sysinv.db.api.DbApi dbapi_instance: Sysinv database API instance
            used to query Helm override data.
        :param int db_app_id: Sysinv application identifier.
        :param str chart_name: Name of the Helm chart to check.

        :returns bool: `True` if the Helm chart override exists and contains
            populated user overrides, otherwise `False`.

        :raises SysinvException: If an unexpected error occurs while accessing
            Helm override data.
        """
        try:
            helm_override = dbapi_instance.helm_override_get(
                app_id=db_app_id,
                namespace=common.HELM_NS_KUBE_SYSTEM,
                name=chart_name,
            )

            return bool(helm_override.user_overrides)

        except exception.NotFound:
            return False

        except Exception as e:
            raise exception.SysinvException(
                f"Unexpected error while checking Helm overrides for '{chart_name}'"
            ) from e

    def _is_subcloud(self, dbapi_instance):
        """Check whether the current system is operating as a subcloud.

        This function determines the distributed cloud role of the local
        system by querying the system record from the Sysinv database.

        :param sysinv.db.api.DbApi dbapi_instance: Sysinv database API instance
            used to retrieve the system record.

        :returns bool: `True` if the current system is a subcloud,
            otherwise `False`.

        :raises SysinvException: If an unexpected error occurs while retrieving
            system information from the database.
        """
        try:
            system = dbapi_instance.isystem_get_one()

            return system.distributed_cloud_role == constants.DISTRIBUTED_CLOUD_ROLE_SUBCLOUD

        except Exception as e:
            raise exception.SysinvException(
                "Failed to retrieve cloud role"
            ) from e

    def _default_oidc_configuration(self, dbapi_instance):
        """Configure default local OIDC settings for the controller.

        This function applies the full local OIDC configuration for a
        controller that does not yet have OIDC set up. It retrieves the OAM
        and management floating IPs, generates the OIDC issuer URL, and
        fetches the LDAP password required for authentication.

        It then performs the following actions in order:
        * Configures the Kubernetes API server OIDC parameters.
        * Applies the OIDC certificate object.
        * Sets Helm user overrides for `oidc-client`, `dex`, and
            `secret-observer` charts.

        :param sysinv.db.api.DbApi dbapi_instance: Sysinv database API
            instance used to retrieve network information and configure
            Kubernetes and Helm parameters.
        """
        LOG.info("Applying default configuration to OIDC")

        issuer_url = self._get_k8s_issuer_url(dbapi_instance)
        oam_ip = self._extract_oam_ip_from_oidc_issuer_url(issuer_url)
        mgmt_ip = self._get_floating_ip_by_net_type(
            dbapi_instance,
            constants.NETWORK_TYPE_MGMT,
        )
        ldap_pwd = self._get_ldap_password()

        self._apply_oidc_certificate(oam_ip)

        tls_ver, tls_ciphers = self._get_platform_tls_config(dbapi_instance)

        self._configure_oidc_client_override(
            dbapi_instance, tls_ver, tls_ciphers)
        self._configure_dex_override(
            dbapi_instance, mgmt_ip, ldap_pwd, tls_ver)
        self._configure_secret_observer_override(dbapi_instance)

    def _apply_oidc_certificate(self, oam_ip):
        """Create the OIDC Certificate.

        This function ensures the `oidc-auth-apps` Certificate resource managed
        by cert-manager exists and is up to date. It deletes any existing
        Certificate object and then recreates it with the correct specification.

        :param str oam_ip: OAM floating IP address used as the certificate's
            common name and IP address.

        :raises SysinvException: If an unexpected error occurs while deleting
            or creating the Certificate resource.
        """
        try:
            api = client.CustomObjectsApi()

            try:
                api.delete_namespaced_custom_object(
                    group=CERTIFICATE_GROUP,
                    version=CERTIFICATE_VERSION,
                    namespace=CERTIFICATE_NAMESPACE,
                    plural=CERTIFICATE_PLURAL,
                    name=CERTIFICATE_NAME,
                )
                LOG.info(
                    "Deleted existing OIDC Certificate %s in namespace %s",
                    CERTIFICATE_NAME, CERTIFICATE_NAMESPACE,
                )

            except ApiException as e:
                if e.status == 404:
                    LOG.info(
                        "OIDC Certificate %s not found in namespace %s",
                        CERTIFICATE_NAME, CERTIFICATE_NAMESPACE,
                    )
                else:
                    raise exception.SysinvException(
                        "Failed to delete existing OIDC Certificate"
                    ) from e

            body = {
                "apiVersion": f"{CERTIFICATE_GROUP}/{CERTIFICATE_VERSION}",
                "kind": "Certificate",
                "metadata": {
                    "name": CERTIFICATE_NAME,
                    "namespace": CERTIFICATE_NAMESPACE,
                },
                "spec": {
                    "secretName": "oidc-auth-apps-certificate",
                    "duration": "2160h",       # 90 days
                    "renewBefore": "360h",     # 15 days
                    "issuerRef": {
                        "name": "system-local-ca",
                        "kind": "ClusterIssuer",
                    },
                    "commonName": oam_ip,
                    "subject": {
                        "organizations": ["StarlingX"],
                        "organizationalUnits": [
                            "StarlingX-system-oidc-auth-apps",
                        ],
                    },
                    "ipAddresses": [oam_ip],
                },
            }

            api.create_namespaced_custom_object(
                group=CERTIFICATE_GROUP,
                version=CERTIFICATE_VERSION,
                namespace=CERTIFICATE_NAMESPACE,
                plural=CERTIFICATE_PLURAL,
                body=body,
            )
            LOG.info(
                "Created new OIDC Certificate %s in namespace %s",
                CERTIFICATE_NAME, CERTIFICATE_NAMESPACE,
            )

        except Exception as e:
            raise exception.SysinvException(
                "Failed to apply OIDC Certificate"
            ) from e

    def _configure_oidc_client_override(self, dbapi_instance,
                                        tls_min_version, tls_cipher_suite):
        """Set Helm override values for the oidc-client chart.

        Links the chart to the correct TLS certificate and CA secret used for
        OIDC communication, and configures TLS version and cipher suites.

        :param sysinv.db.api.DbApi dbapi_instance: Sysinv database API instance
            used to update Helm user overrides.
        :param str tls_min_version: Platform TLS minimum version constant.
        :param str tls_cipher_suite: Comma-separated IANA cipher suite names.

        :raises SysinvException: If applying the Helm override configuration
            fails.
        """
        client_tls_version = DEX_TLS_VERSION_MAP.get(tls_min_version, '1.2')
        cipher_list = [c.strip() for c in tls_cipher_suite.split(',')
                       if c.strip()]

        values = {
            "tlsName": "oidc-auth-apps-certificate",
            "config": {
                "issuer_root_ca": "/home/ca.crt",
                "issuer_root_ca_secret": "oidc-auth-apps-certificate",
                "tlsMinVersion": client_tls_version,
                "tlsCipherSuites": cipher_list,
            },
        }

        try:
            self._update_helm_user_overrides(
                dbapi_instance=dbapi_instance,
                app_name=constants.HELM_APP_OIDC_AUTH,
                chart_name=app_constants.HELM_CHART_OIDC_CLIENT,
                namespace=common.HELM_NS_KUBE_SYSTEM,
                values_dict=values,
            )
        except Exception as e:
            raise exception.SysinvException(
                "Failed to configure oidc-client Helm override"
            ) from e

    def _configure_dex_override(self, dbapi_instance, mgmt_ip, ldap_pwd,
                                tls_min_version):
        """Set Helm override values for the dex chart.

        Configures Dex to authenticate against LDAP, using the management IP and
        provided LDAP password. The override also mounts the OIDC certificate
        for TLS communication and sets the minimum TLS version.

        :param sysinv.db.api.DbApi dbapi_instance: Sysinv database API instance
            used to update Helm user overrides.
        :param str mgmt_ip: Management floating IP address used for the LDAP
            host.
        :param str ldap_pwd: Password for the LDAP bindDN user.
        :param str tls_min_version: Platform TLS minimum version constant.

        :raises SysinvException: If applying the Helm override configuration
            fails.
        """
        ip = IPAddress(mgmt_ip)
        host = f"[{mgmt_ip}]" if ip.version == 6 else mgmt_ip

        dex_tls_version = DEX_TLS_VERSION_MAP.get(tls_min_version, '1.2')

        values = {
            "config": {
                "expiry": {
                    "idTokens": "24h"
                },
                "web": {
                    "tlsMinVersion": dex_tls_version,
                },
                "connectors": [
                    {
                        "type": "ldap",
                        "name": "ldap-1",
                        "id": "ldap-1",
                        "config": {
                            "host": f"{host}:636",
                            "rootCA": "/etc/ssl/certs/adcert/ca.crt",
                            "insecureNoSSL": False,
                            "insecureSkipVerify": False,
                            "bindDN": "CN=ldapadmin,DC=cgcs,DC=local",
                            "bindPW": ldap_pwd,
                            "usernamePrompt": "Username",
                            "userSearch": {
                                "baseDN": "ou=People,dc=cgcs,dc=local",
                                "filter": "(objectClass=posixAccount)",
                                "username": "uid",
                                "idAttr": "DN",
                                "emailAttr": "uid",
                                "nameAttr": "gecos",
                            },
                            "groupSearch": {
                                "baseDN": "ou=Group,dc=cgcs,dc=local",
                                "filter": "(objectClass=posixGroup)",
                                "userMatchers": [
                                    {
                                        "userAttr": "uid",
                                        "groupAttr": "memberUid"
                                    }
                                ],
                                "nameAttr": "cn",
                            },
                        },
                    }
                ],
            },
            "volumeMounts": [
                {"mountPath": "/etc/ssl/certs/adcert", "name": "certdir"},
                {"mountPath": "/etc/dex/tls", "name": "https-tls"},
            ],
            "volumes": [
                {
                    "name": "certdir",
                    "secret": {"secretName": "oidc-auth-apps-certificate"},
                },
                {
                    "name": "https-tls",
                    "secret": {
                        "defaultMode": 420,
                        "secretName": "oidc-auth-apps-certificate",
                    },
                },
            ],
        }

        self._update_helm_user_overrides(
            dbapi_instance=dbapi_instance,
            app_name=constants.HELM_APP_OIDC_AUTH,
            chart_name=app_constants.HELM_CHART_DEX,
            namespace=common.HELM_NS_KUBE_SYSTEM,
            values_dict=values,
        )

    def _configure_secret_observer_override(self, dbapi_instance):
        """Set Helm override values for the secret-observer chart.

        Configures the chart to monitor the OIDC certificate secrets and restart
        dependent deployments when the secrets are updated.

        :param sysinv.db.api.DbApi dbapi_instance: Sysinv database API instance
            used to update Helm user overrides.

        :raises SysinvException: If applying the Helm override configuration
            fails.
        """
        values = {
            "cronSchedule": "*/15 * * * *",
            "observedSecrets": [
                {
                    "secretName": "oidc-auth-apps-certificate",
                    "filename": "ca.crt",
                    "deploymentToRestart": "stx-oidc-client",
                },
                {
                    "secretName": "oidc-auth-apps-certificate",
                    "filename": "tls.crt",
                    "deploymentToRestart": "stx-oidc-client",
                },
                {
                    "secretName": "oidc-auth-apps-certificate",
                    "filename": "tls.crt",
                    "deploymentToRestart": "oidc-dex",
                },
            ],
        }

        self._update_helm_user_overrides(
            dbapi_instance=dbapi_instance,
            app_name=constants.HELM_APP_OIDC_AUTH,
            chart_name=app_constants.HELM_CHART_SECRET_OBSERVER,
            namespace=common.HELM_NS_KUBE_SYSTEM,
            values_dict=values,
        )

    def _update_helm_user_overrides(self, dbapi_instance, app_name, chart_name,
                                    namespace, values_dict):
        """Create or update Helm user_overrides for a chart.

        Serializes the provided values into YAML and ensures that a
        `user_overrides` entry exists for the specified Helm chart. If the
        override already exists, it is updated; otherwise, it is created.

        :param sysinv.db.api.DbApi dbapi_instance: Sysinv database API instance
            used to manage Helm overrides.
        :param str app_name: Helm application name (for example,
            ``oidc-auth-apps``).
        :param str chart_name: Helm chart name within the application.
        :param str namespace: Kubernetes namespace where the chart is deployed.
        :param dict values_dict: Values to serialize into ``user_overrides``.

        :raises SysinvException: If the application cannot be retrieved or if
            the Helm override cannot be created or updated.
        """
        try:
            db_app = dbapi_instance.kube_app_get(app_name)
        except Exception as e:
            raise exception.SysinvException(
                f"Failed to get kube app '{app_name}'"
            ) from e

        user_overrides = yaml.safe_dump(
            values_dict,
            default_flow_style=False,
            sort_keys=False,
        )

        try:
            # Try to get existing override
            dbapi_instance.helm_override_get(
                app_id=db_app.id,
                name=chart_name,
                namespace=namespace,
            )

            LOG.info(
                "Updating Helm user_overrides for app=%s chart=%s ns=%s",
                app_name, chart_name, namespace,
            )

            dbapi_instance.helm_override_update(
                db_app.id,
                chart_name,
                namespace,
                {'user_overrides': user_overrides},
            )

        except exception.NotFound:
            LOG.info(
                "Creating Helm user_overrides for app=%s chart=%s ns=%s",
                app_name, chart_name, namespace,
            )

            dbapi_instance.helm_override_create({
                'app_id': db_app.id,
                'name': chart_name,
                'namespace': namespace,
                'user_overrides': user_overrides,
                'system_overrides': None,
            })

        except Exception as e:
            raise exception.SysinvException(
                f"Failed to set Helm user_overrides for {app_name}/{chart_name}"
            ) from e

    def _get_platform_tls_config(self, dbapi_instance):
        """Read TLS min version and cipher suite from platform service parameters.

        :param sysinv.db.api.DbApi dbapi_instance: Sysinv database API instance.
        :returns tuple: (tls_min_version, tls_cipher_suite) strings.
        """
        return get_platform_tls_config(dbapi_instance)

    def _load_kube_config(self):
        """Load and initialize the Kubernetes admin configuration.

        Loads the Kubernetes administrative configuration file to initialize
        the Kubernetes client context for subsequent API operations.
        """
        config.load_kube_config(kube_utils.KUBERNETES_ADMIN_CONF)
        cfg = client.Configuration().get_default_copy()
        cfg.verify_ssl = True
        client.Configuration.set_default(cfg)

    def _get_floating_ip_by_net_type(self, dbapi_instance, network_type):
        """Retrieve the floating IP for a given network type.

        Queries the Sysinv database to obtain the floating IP address
        associated with the specified network type (e.g., OAM, MGMT, or
        System Controller OAM).

        :param sysinv.db.api.DbApi dbapi_instance: Sysinv database API instance
            used to access network and address pool information.
        :param str network_type: Network type whose floating IP should be
            retrieved.
        :returns str: Floating IP address corresponding to the specified
            network type.

        :raises SysinvException: If the network, address pool, or floating IP
            cannot be retrieved from the database.
        """
        try:
            net = dbapi_instance.network_get_by_type(network_type)
            pool = dbapi_instance.address_pool_get(net.pool_uuid)
            floating_ip = pool.floating_address

            return floating_ip

        except Exception as e:
            raise exception.SysinvException(
                    "Failed to retrieve OAM floating IP"
            ) from e

    def _get_ldap_password(self, user="ldapadmin", service="ldap"):
        """Retrieve the LDAP password from the system keyring.

        Looks up the password for the specified user and service stored in
        the system keyring.

        :param str user: Username associated with the keyring entry.
        :param str service: Service name for the keyring entry.

        :returns str: Password retrieved from the system keyring.

        :raises SysinvException: If the password is missing or cannot be
            retrieved from the keyring.
        """
        try:
            password = keyring.get_password(service, user)
            if not password:
                raise exception.SysinvException(
                    f"No password found in keyring for {service}/{user}"
                )

            return password
        except Exception as e:
            raise exception.SysinvException(
                "Failed to retrieve LDAP password from keyring"
            ) from e

    def _extract_oam_ip_from_oidc_issuer_url(self, issuer_url):
        """Extract the OAM floating IP address from an OIDC issuer URL.

        This function parses the provided OIDC issuer URL and extracts the OAM
        floating IP address used to construct it. Both IPv4 and IPv6 address
        formats are supported.

        Expected URL formats:
        - https://<oam_ip>:<port>/dex
        - https://[<oam_ip>]:<port>/dex

        :param str issuer_url: Fully formatted OIDC issuer URL.

        :returns str: OAM floating IP address extracted from the URL.

        :raises SysinvException: If the issuer URL is invalid or the IP address
            cannot be parsed.
        """
        try:
            parsed = urlparse(issuer_url)

            if parsed.scheme != "https" or not parsed.hostname:
                raise ValueError("Invalid issuer URL format")

            oam_ip = parsed.hostname

            # Validate extracted IP address
            IPAddress(oam_ip)

            return oam_ip

        except Exception as e:
            raise exception.SysinvException(
                "Invalid OIDC issuer URL"
            ) from e

    def _dump_oidc_login_config(self, dbapi_instance):
        """Dump OIDC login parameters to a well-known file.

        Writes oidc-issuer-url, oidc-client-id, oidc-client-secret, and
        oidc-issuer-ca to a YAML file that kubeconfig-setup can read to
        configure oidc-login exec blocks automatically.

        :param sysinv.db.api.DbApi dbapi_instance: Sysinv database API instance.

        :raises SysinvException: If any required OIDC login parameter is
            missing or if the config file cannot be written.
        """
        issuer_url = self._get_k8s_issuer_url(dbapi_instance)
        client_id = self._get_oidc_client_id(dbapi_instance)
        client_secret = self._get_oidc_client_secret(dbapi_instance)
        issuer_ca = self._get_issuer_ca_cert()

        missing = []
        if not issuer_url:
            missing.append('oidc-issuer-url')
        if not client_id:
            missing.append('oidc-client-id')
        if not client_secret:
            missing.append('oidc-client-secret')
        if not issuer_ca:
            missing.append('oidc-issuer-ca')

        if missing:
            raise exception.SysinvException(
                "OIDC login config incomplete, missing: %s"
                % ', '.join(missing)
            )

        config_data = {
            'oidc-issuer-url': issuer_url,
            'oidc-client-id': client_id,
            'oidc-client-secret': client_secret,
            'oidc-issuer-ca': issuer_ca,
        }

        config_path = app_constants.OIDC_LOGIN_CONFIG_FILE
        tmp_path = config_path + '.tmp'
        try:
            with open(tmp_path, 'w') as f:
                yaml.safe_dump(config_data, f, default_flow_style=False)
            os.chmod(tmp_path, 0o644)
            os.rename(tmp_path, config_path)
            LOG.info("OIDC login config written to %s", config_path)
        except Exception as e:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise exception.SysinvException(
                "Failed to write OIDC login config to %s: %s"
                % (config_path, e)
            ) from e

    def _get_issuer_ca_cert(self):
        try:
            dbapi_instance = dbapi.get_instance()
            secret_name = self._get_dex_tls_secret_name(dbapi_instance)

            k8s_v1_client = client.CoreV1Api()
            secret = k8s_v1_client.read_namespaced_secret(
                name=secret_name,
                namespace=common.HELM_NS_KUBE_SYSTEM,
            )
            ca_bytes = secret.data.get('ca.crt')
            if not ca_bytes:
                raise exception.SysinvException(
                    f"Secret '{secret_name}' has no ca.crt"
                )
            return ca_bytes
        except exception.SysinvException:
            raise
        except Exception as e:
            raise exception.SysinvException(
                "Failed to read issuer CA cert from dex TLS secret"
            ) from e

    def _get_dex_tls_secret_name(self, dbapi_instance):
        """Dex TLS server certificate is placed at /etc/dex/tls.
        So this method returns the secret name that contains this cert.

        Reads the dex Helm user overrides and finds the volume whose
        corresponding volumeMount targets /etc/dex/tls, then returns
        the secretName from that volume.

        :param sysinv.db.api.DbApi dbapi_instance: Sysinv database API instance.
        :returns str: Name of the Kubernetes secret mounted at /etc/dex/tls.
        :raises SysinvException: If the secret name cannot be determined.
        """
        try:
            db_app = dbapi_instance.kube_app_get(constants.HELM_APP_OIDC_AUTH)
            helm_override = dbapi_instance.helm_override_get(
                app_id=db_app.id,
                name=app_constants.HELM_CHART_DEX,
                namespace=common.HELM_NS_KUBE_SYSTEM,
            )

            if not helm_override.user_overrides:
                raise exception.SysinvException(
                    "Dex chart has no user overrides configured"
                )

            overrides = yaml.safe_load(helm_override.user_overrides)
            volume_mounts = overrides.get('volumeMounts', [])
            volumes = overrides.get('volumes', [])

            # Find the volume name mounted at /etc/dex/tls
            tls_volume_name = None
            for vm in volume_mounts:
                if vm.get('mountPath') == '/etc/dex/tls':
                    tls_volume_name = vm.get('name')
                    break

            if not tls_volume_name:
                raise exception.SysinvException(
                    "No volumeMount found for /etc/dex/tls in dex overrides"
                )

            # Find the secret name for that volume
            for vol in volumes:
                if vol.get('name') == tls_volume_name:
                    secret_name = vol.get('secret', {}).get('secretName')
                    if secret_name:
                        LOG.info("Dex TLS secret name resolved to '%s'", secret_name)
                        return secret_name

            raise exception.SysinvException(
                f"No secret found for volume '{tls_volume_name}' in dex overrides"
            )

        except exception.SysinvException:
            raise
        except Exception as e:
            raise exception.SysinvException(
                "Failed to determine dex TLS secret name from overrides"
            ) from e

    def _get_oidc_client_id(self, dbapi_instance):
        try:
            param = dbapi_instance.service_parameter_get_one(
                constants.SERVICE_TYPE_KUBERNETES,
                constants.SERVICE_PARAM_SECTION_KUBERNETES_APISERVER,
                constants.SERVICE_PARAM_NAME_OIDC_CLIENT_ID,
            )
            return param.value
        except exception.NotFound:
            return app_constants.DEFAULT_OIDC_CLIENT_ID

    def _get_oidc_client_secret(self, dbapi_instance):
        try:
            db_app = dbapi_instance.kube_app_get(constants.HELM_APP_OIDC_AUTH)
            helm_override = dbapi_instance.helm_override_get(
                app_id=db_app.id,
                name=app_constants.HELM_CHART_OIDC_CLIENT,
                namespace=common.HELM_NS_KUBE_SYSTEM,
            )
            if helm_override.user_overrides:
                overrides = yaml.safe_load(helm_override.user_overrides)
                secret = overrides.get('config', {}).get('client_secret')
                if secret:
                    return secret
        except Exception as e:
            raise exception.SysinvException(
                "Failed to retrieve OIDC client secret from Helm overrides"
            ) from e

        return app_constants.DEFAULT_OIDC_CLIENT_SECRET
