#
# Copyright (c) 2020,2026 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

from k8sapp_oidc.common import constants as app_constants
from k8sapp_oidc.helm.dex_base import DexBaseHelm
from k8sapp_oidc.helm.dex_base import DEX_TLS_VERSION_MAP

from sysinv.common import exception
from sysinv.helm import common


class OidcClientHelm(DexBaseHelm):
    """Class to encapsulate helm operations for the OIDC client chart"""

    CHART = app_constants.HELM_CHART_OIDC_CLIENT

    SERVICE_NAME = 'oidc_client'

    def get_namespaces(self):
        return self.SUPPORTED_NAMESPACES

    def get_overrides(self, namespace=None):
        oam_url = self._format_url_address(self._get_oam_address())

        tls_min_version, tls_cipher_suite = self._get_platform_tls_config()
        # OIDC Client Go binary uses the same "1.2"/"1.3" format as Dex
        client_tls_version = DEX_TLS_VERSION_MAP.get(tls_min_version, '1.2')
        # OIDC Client uses IANA cipher names directly (Go native)
        cipher_list = [c.strip() for c in tls_cipher_suite.split(',')
                       if c.strip()]

        overrides = {
            common.HELM_NS_KUBE_SYSTEM: {
                'config': {
                    'client_id': self._get_client_id(),
                    'client_secret': self._get_client_secret(),
                    'issuer': "https://%s:%s/dex" % (oam_url, self.DEX_NODE_PORT),
                    'issuer_root_ca': '/home/dex-ca.pem',
                    'listen': 'https://0.0.0.0:5555',
                    'redirect_uri': "https://%s:%s/callback" % (oam_url, self.OIDC_CLIENT_NODE_PORT),
                    'tlsMinVersion': client_tls_version,
                    'tlsCipherSuites': cipher_list,
                },
                'service': {
                    'nodePort': self.OIDC_CLIENT_NODE_PORT
                },
                'replicas': self._num_replicas_for_platform_app(),
            }
        }

        if namespace in self.SUPPORTED_NAMESPACES:
            return overrides[namespace]
        elif namespace:
            raise exception.InvalidHelmNamespace(chart=self.CHART,
                                                 namespace=namespace)
        else:
            return overrides
