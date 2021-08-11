#
# Copyright (c) 2021 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

from k8sapp_oidc.common import constants as app_constants
from k8sapp_oidc.helm.dex_base import DexBaseHelm

from sysinv.common import exception
from sysinv.helm import common


class SecretObserverHelm(DexBaseHelm):
    """Class to encapsulate helm operations for the secret observer chart"""

    CHART = app_constants.HELM_CHART_SECRET_OBSERVER
    SERVICE_NAME = 'secret-observer'

    def get_namespaces(self):
        return self.SUPPORTED_NAMESPACES

    def get_overrides(self, namespace=None):
        overrides = {
            common.HELM_NS_KUBE_SYSTEM: {}
        }

        if namespace in self.SUPPORTED_NAMESPACES:
            return overrides[namespace]
        elif namespace:
            raise exception.InvalidHelmNamespace(chart=self.CHART,
                                                 namespace=namespace)
        else:
            return overrides
