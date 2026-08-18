#
# Copyright (c) 2020-2026 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

from oslo_log import log as logging

from k8sapp_oidc.common import constants as app_constants
from k8sapp_oidc.helm.dex_base import DexBaseHelm
from k8sapp_oidc.helm.dex_base import DEX_TLS_VERSION_MAP
from k8sapp_oidc.helm.dex_base import get_subcloud_oam_floating_ips
from k8sapp_oidc.helm.dex_base import OIDC_LOGIN_CALLBACK_PORT

from sysinv.common import exception
from sysinv.helm import common

LOG = logging.getLogger(__name__)


class Dex(DexBaseHelm):
    """Class to encapsulate helm operations for the dex chart"""

    CHART = app_constants.HELM_CHART_DEX

    def get_namespaces(self):
        return self.SUPPORTED_NAMESPACES

    def _get_static_clients(self):
        static_clients = []

        oam_address = self._format_url_address(self._get_oam_address())

        redirect_uris = [
            "https://%s:%s/callback" % (oam_address, self.OIDC_CLIENT_NODE_PORT),
            "https://%s:%s/oauth2/callback" % (oam_address, self.OAUTH2_PROXY_PORT),
        ]

        # On a DC system controller with centralized OIDC, add redirect
        # URIs for the oidc-login kubectl plugin callback listener.
        # The plugin listens on port 8000 and the redirect must match
        # the address the user's browser resolves to:
        #   - localhost:8000 — remote_cli from a workstation
        #   - <system_controller_OAM>:8000 — local CLI on the central
        #   - <subcloud_OAM>:8000 — local CLI on a subcloud
        if self._is_distributed_cloud_role_system_controller():
            redirect_uris.append(
                "http://localhost:%s" % OIDC_LOGIN_CALLBACK_PORT)
            redirect_uris.append(
                "http://%s:%s" % (oam_address, OIDC_LOGIN_CALLBACK_PORT))

            subcloud_oam_ips = get_subcloud_oam_floating_ips()
            for sc_oam_ip in subcloud_oam_ips:
                sc_address = self._format_url_address(sc_oam_ip)
                redirect_uris.append(
                    "http://%s:%s" % (sc_address, OIDC_LOGIN_CALLBACK_PORT)
                )
            if subcloud_oam_ips:
                LOG.info("Added %d subcloud redirect URIs to dex "
                         "static client", len(subcloud_oam_ips))

        oidc_client = {
            'id': self._get_client_id(),
            'redirectURIs': redirect_uris,
            'name': 'STX OIDC Client app',
            'secret': self._get_client_secret()
        }

        static_clients.append(oidc_client)

        return static_clients

    def get_overrides(self, namespace=None):

        tls_min_version, _ = self._get_platform_tls_config()
        dex_tls_version = DEX_TLS_VERSION_MAP.get(tls_min_version, '1.2')

        env = {
            'name': 'KUBERNETES_POD_NAMESPACE',
            'value': common.HELM_NS_KUBE_SYSTEM
        }

        service = {
            'type': 'NodePort',
            'ports': {
                'https': {
                    'nodePort': self.DEX_NODE_PORT
                }
            }
        }

        overrides = {
            common.HELM_NS_KUBE_SYSTEM: {
                'config': {
                    'issuer': "https://%s:%s/dex" % (self._format_url_address(self._get_oam_address()),
                                                     self.DEX_NODE_PORT),
                    'staticClients': self._get_static_clients(),
                    'web': {
                        'tlsMinVersion': dex_tls_version,
                    },
                },
                'replicaCount': self._num_replicas_for_platform_app(),
                'env': env,
                'service': service
            }
        }

        if namespace in self.SUPPORTED_NAMESPACES:
            return overrides[namespace]
        elif namespace:
            raise exception.InvalidHelmNamespace(chart=self.CHART,
                                                 namespace=namespace)
        else:
            return overrides
