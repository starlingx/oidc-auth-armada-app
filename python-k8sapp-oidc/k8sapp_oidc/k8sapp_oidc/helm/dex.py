#
# Copyright (c) 2020 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

from k8sapp_oidc.common import constants as app_constants
from k8sapp_oidc.helm.dex_base import DexBaseHelm

from sysinv.common import exception
from sysinv.helm import common


class Dex(DexBaseHelm):
    """Class to encapsulate helm operations for the dex chart"""

    CHART = app_constants.HELM_CHART_DEX

    def get_namespaces(self):
        return self.SUPPORTED_NAMESPACES

    def _get_static_clients(self):
        static_clients = []

        oidc_client = {
            'id': self._get_client_id(),
            'redirectURIs': ["https://%s:%s/callback" %
                             (self._format_url_address(self._get_oam_address()),
                              self.OIDC_CLIENT_NODE_PORT)],
            'name': 'STX OIDC Client app',
            'secret': self._get_client_secret()
        }

        static_clients.append(oidc_client)

        return static_clients

    def get_overrides(self, namespace=None):

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
