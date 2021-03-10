#
# Copyright (c) 2020 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

from k8sapp_oidc.common import constants as app_constants
from k8sapp_oidc.helm.dex_base import DexBaseHelm

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
        overrides = {
            common.HELM_NS_KUBE_SYSTEM: {
                'config': {
                    'client_id': self._get_client_id(),
                    'client_secret': self._get_client_secret(),
                    'issuer': "https://%s:%s/dex" % (oam_url, self.DEX_NODE_PORT),
                    'issuer_root_ca': '/home/dex-ca.pem',
                    'listen': 'https://0.0.0.0:5555',
                    'redirect_uri': "https://%s:%s/callback" % (oam_url, self.OIDC_CLIENT_NODE_PORT),
                },
                'service': {
                    'nodePort': self.OIDC_CLIENT_NODE_PORT
                },
                'replicas': self._num_provisioned_controllers(),
            }
        }

        if namespace in self.SUPPORTED_NAMESPACES:
            return overrides[namespace]
        elif namespace:
            raise exception.InvalidHelmNamespace(chart=self.CHART,
                                                 namespace=namespace)
        else:
            return overrides
