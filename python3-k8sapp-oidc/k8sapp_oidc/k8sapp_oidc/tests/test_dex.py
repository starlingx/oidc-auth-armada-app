#
# Copyright (c) 2020 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

from k8sapp_oidc.common import constants as app_constants
from k8sapp_oidc.tests import test_plugins

from sysinv.common import constants
from sysinv.common import utils
from sysinv.db import api as dbapi
from sysinv.helm import common

from sysinv.tests.db import base as dbbase
from sysinv.tests.db import utils as dbutils
from sysinv.tests.helm import base


class DexTestCase(test_plugins.K8SAppOidcAppMixin,
                  base.HelmTestCaseMixin):

    def setUp(self):
        super(DexTestCase, self).setUp()
        self.app = dbutils.create_test_app(name='oidc-auth-apps')
        self.dbapi = dbapi.get_instance()

    def test_issuer(self):
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_DEX,
            cnamespace=common.HELM_NS_KUBE_SYSTEM)

        oam_addr_name = utils.format_address_name(constants.CONTROLLER_HOSTNAME,
                                                  constants.NETWORK_TYPE_OAM)
        oam_address = self.dbapi.address_get_by_name(oam_addr_name)

        # add some debug printing
        print("Number of addresses (%s): %s" %
            (type(oam_address), len(oam_address)))
        i = 0
        while i < len(oam_address):
            print("Address[%s]: %s" % (i, str(oam_address[i].address)))
            i += 1

        # There should be one address
        oam_url = utils.format_url_address(oam_address[0].address)
        print("Url Address: %s" % oam_url)
        config_issuer = "https://%s:30556/dex" % oam_url
        self.assertOverridesParameters(overrides, {
            # issuer is set properly
            'config': {'issuer': config_issuer}
        })

        # Complain if there is more than one address.
        # It already failed if the list was empty
        if len(oam_address) > 1:
            raise ValueError("Too many addresses in returned list")


class DexIPv4ControllerHostTestCase(DexTestCase,
                                    dbbase.ProvisionedControllerHostTestCase):

    def test_replicas(self):
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_DEX,
            cnamespace=common.HELM_NS_KUBE_SYSTEM)

        self.assertOverridesParameters(overrides, {
            # 1 replica for 1 controller
            'replicaCount': 1
        })


class DexIPv6AIODuplexSystemTestCase(DexTestCase,
                                     dbbase.BaseIPv6Mixin,
                                     dbbase.ProvisionedAIODuplexSystemTestCase):

    def test_replicas(self):
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_DEX,
            cnamespace=common.HELM_NS_KUBE_SYSTEM)

        self.assertOverridesParameters(overrides, {
            # 2 replicas for 2 controllers
            'replicaCount': 2
        })
