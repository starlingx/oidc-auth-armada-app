#
# Copyright (c) 2020,2026 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

from oslo_log import log as logging

from sysinv.common import constants

from sysinv.helm import base
from sysinv.helm import common

LOG = logging.getLogger(__name__)

# Map platform TLS version constants to Dex format ("1.2", "1.3")
DEX_TLS_VERSION_MAP = {
    constants.SERVICE_PARAM_PLATFORM_TLS_VERSION_TLS12: '1.2',
    constants.SERVICE_PARAM_PLATFORM_TLS_VERSION_TLS13: '1.3',
}


def get_platform_tls_config(dbapi_instance):
    """Read TLS min version and cipher suite from platform service parameters.

    :param dbapi_instance: Sysinv database API instance.
    :returns tuple: (tls_min_version, tls_cipher_suite) strings.
    """
    tls_min_version = \
        constants.SERVICE_PARAM_PLATFORM_TLS_MIN_VERSION_DEFAULT
    tls_cipher_suite = \
        constants.SERVICE_PARAM_PLATFORM_TLS_CIPHER_SUITE_DEFAULT

    try:
        parms = dbapi_instance.service_parameter_get_all(
            service=constants.SERVICE_TYPE_PLATFORM,
            section=constants.SERVICE_PARAM_SECTION_PLATFORM_CONFIG)
        for p in parms:
            if p.name == \
                    constants.SERVICE_PARAM_NAME_PLATFORM_TLS_MIN_VERSION:
                tls_min_version = p.value
            elif p.name == \
                    constants.SERVICE_PARAM_NAME_PLATFORM_TLS_CIPHER_SUITE:
                tls_cipher_suite = p.value
    except Exception:
        LOG.warning("Failed to read TLS service parameters, "
                    "using defaults for OIDC overrides")

    return tls_min_version, tls_cipher_suite


class DexBaseHelm(base.BaseHelm):
    """Class to encapsulate helm operations for the dex chart"""

    SUPPORTED_NAMESPACES = base.BaseHelm.SUPPORTED_NAMESPACES + \
        [common.HELM_NS_KUBE_SYSTEM]
    SUPPORTED_APP_NAMESPACES = {
        constants.HELM_APP_OIDC_AUTH:
            base.BaseHelm.SUPPORTED_NAMESPACES + [common.HELM_NS_KUBE_SYSTEM],
    }

    # OIDC client and DEX Node ports
    OIDC_CLIENT_NODE_PORT = 30555
    DEX_NODE_PORT = 30556

    @property
    def CHART(self):
        # subclasses must define the property: CHART='name of chart'
        # if an author of a new chart forgets this, NotImplementedError is raised
        raise NotImplementedError

    def get_namespaces(self):
        return self.SUPPORTED_NAMESPACES

    def _get_client_id(self):
        return 'stx-oidc-client-app'

    def _get_client_secret(self):
        return 'St8rlingX'

    def _get_platform_tls_config(self):
        """Read TLS min version and cipher suite from platform service parameters.

        Returns a tuple of (tls_min_version, tls_cipher_suite) using
        platform defaults if the parameters are not configured.
        """
        return get_platform_tls_config(self.dbapi)
