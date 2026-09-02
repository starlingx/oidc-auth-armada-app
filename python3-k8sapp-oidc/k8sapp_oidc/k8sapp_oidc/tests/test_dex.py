#
# Copyright (c) 2020,2026 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

import json
from unittest import mock

from k8sapp_oidc.common import constants as app_constants
from k8sapp_oidc.helm import dex as dex_module
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

    def test_static_clients_no_dc(self):
        """On a non-DC system, base redirectURIs plus local OAM and
        localhost :8000."""
        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_DEX,
            cnamespace=common.HELM_NS_KUBE_SYSTEM)

        static_clients = overrides['config']['staticClients']
        self.assertEqual(len(static_clients), 1)

        redirect_uris = static_clients[0]['redirectURIs']
        # Should have exactly 4 URIs: callback + oauth2/callback +
        # the local OAM oidc-login callback (port 8000) + localhost:8000
        self.assertEqual(len(redirect_uris), 4)
        self.assertTrue(redirect_uris[0].endswith(':30555/callback'))
        self.assertTrue(redirect_uris[1].endswith(':5000/oauth2/callback'))
        self.assertTrue(redirect_uris[2].startswith('http://'))
        self.assertTrue(redirect_uris[2].endswith(':8000'))
        self.assertIn('http://localhost:8000', redirect_uris)

    @mock.patch.object(dex_module, 'get_subcloud_oam_floating_ips')
    def test_static_clients_dc_system_controller(self, mock_get_sc_ips):
        """On a DC system controller, redirect URIs include subclouds."""
        # Set up as system controller
        system = self.dbapi.isystem_get_one()
        self.dbapi.isystem_update(system.uuid, {
            'distributed_cloud_role':
                constants.DISTRIBUTED_CLOUD_ROLE_SYSTEMCONTROLLER
        })

        mock_get_sc_ips.return_value = ['10.10.10.3', '10.10.10.4']

        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_DEX,
            cnamespace=common.HELM_NS_KUBE_SYSTEM)

        static_clients = overrides['config']['staticClients']
        self.assertEqual(len(static_clients), 1)

        redirect_uris = static_clients[0]['redirectURIs']
        # 2 base URIs + localhost + system controller OAM + 2 subcloud URIs
        self.assertEqual(len(redirect_uris), 6)
        self.assertIn('http://localhost:8000', redirect_uris)
        self.assertIn('http://10.10.10.3:8000', redirect_uris)
        self.assertIn('http://10.10.10.4:8000', redirect_uris)
        # system controller OAM redirect URI is also present
        oam_uris = [u for u in redirect_uris if ':8000' in u
                    and 'localhost' not in u
                    and '10.10.10.3' not in u
                    and '10.10.10.4' not in u]
        self.assertEqual(len(oam_uris), 1)

    @mock.patch.object(dex_module, 'get_subcloud_oam_floating_ips')
    def test_static_clients_dc_system_controller_ipv6(self, mock_get_sc_ips):
        """IPv6 subcloud OAM addresses are formatted with brackets."""
        system = self.dbapi.isystem_get_one()
        self.dbapi.isystem_update(system.uuid, {
            'distributed_cloud_role':
                constants.DISTRIBUTED_CLOUD_ROLE_SYSTEMCONTROLLER
        })

        mock_get_sc_ips.return_value = ['fd01::3', 'fd01::4']

        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_DEX,
            cnamespace=common.HELM_NS_KUBE_SYSTEM)

        static_clients = overrides['config']['staticClients']
        redirect_uris = static_clients[0]['redirectURIs']
        # 2 base URIs + localhost + system controller OAM + 2 subcloud URIs
        self.assertEqual(len(redirect_uris), 6)
        self.assertIn('http://localhost:8000', redirect_uris)
        self.assertIn('http://[fd01::3]:8000', redirect_uris)
        self.assertIn('http://[fd01::4]:8000', redirect_uris)

    @mock.patch.object(dex_module, 'get_subcloud_oam_floating_ips')
    def test_static_clients_dc_no_subclouds(self, mock_get_sc_ips):
        """DC system controller with no managed subclouds."""
        system = self.dbapi.isystem_get_one()
        self.dbapi.isystem_update(system.uuid, {
            'distributed_cloud_role':
                constants.DISTRIBUTED_CLOUD_ROLE_SYSTEMCONTROLLER
        })

        mock_get_sc_ips.return_value = []

        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_DEX,
            cnamespace=common.HELM_NS_KUBE_SYSTEM)

        static_clients = overrides['config']['staticClients']
        redirect_uris = static_clients[0]['redirectURIs']
        # 2 base URIs + localhost + system controller OAM
        self.assertEqual(len(redirect_uris), 4)
        self.assertIn('http://localhost:8000', redirect_uris)

    @mock.patch.object(dex_module, 'get_subcloud_oam_floating_ips')
    def test_static_clients_dc_10k_subclouds_within_helm_limit(
            self, mock_get_sc_ips):
        """Verify 10,000 worst-case IPv6 subclouds stay within Helm limits.

        Kubernetes Secrets have a 1 MiB size limit. Helm stores each
        release as a gzipped+base64-encoded Secret. This test ensures
        the generated overrides remain well under that threshold even
        at extreme scale with maximum-length IPv6 redirect URIs.
        """
        import gzip
        import base64

        system = self.dbapi.isystem_get_one()
        self.dbapi.isystem_update(system.uuid, {
            'distributed_cloud_role':
                constants.DISTRIBUTED_CLOUD_ROLE_SYSTEMCONTROLLER
        })

        # Generate 10,000 unique worst-case IPv6 addresses
        # (fully expanded, no :: shorthand)
        num_subclouds = 10000
        subcloud_ips = []
        for i in range(num_subclouds):
            # Distribute across all 4 low hextets for uniqueness
            a = (i >> 12) & 0xffff
            b = (i >> 8) & 0xffff
            c = (i >> 4) & 0xffff
            d = i & 0xffff
            ip = 'fd01:%04x:%04x:%04x:%04x:%04x:%04x:%04x' % (
                0xffff, 0xffff, 0xffff, a, b, c, d)
            subcloud_ips.append(ip)

        mock_get_sc_ips.return_value = subcloud_ips

        overrides = self.operator.get_helm_chart_overrides(
            app_constants.HELM_CHART_DEX,
            cnamespace=common.HELM_NS_KUBE_SYSTEM)

        # Validate all subcloud URIs are present
        static_clients = overrides['config']['staticClients']
        redirect_uris = static_clients[0]['redirectURIs']
        # 2 base + localhost + system controller OAM + 10000 subclouds
        expected_count = 4 + num_subclouds
        self.assertEqual(len(redirect_uris), expected_count)

        # Measure serialized size — Helm stores overrides as JSON
        overrides_json = json.dumps(overrides).encode('utf-8')

        # Simulate Helm release secret encoding: gzip -> base64
        compressed = gzip.compress(overrides_json)
        helm_secret_payload = base64.b64encode(compressed)

        # Kubernetes Secret hard limit: 1 MiB (1,048,576 bytes)
        k8s_secret_limit = 1048576

        # The Helm release secret includes more than just overrides
        # (chart metadata, rendered templates, etc). Use 50% of the
        # limit as our budget for overrides alone to leave headroom.
        overrides_budget = k8s_secret_limit // 2

        self.assertLess(
            len(helm_secret_payload), overrides_budget,
            "Helm override payload (%d bytes gzip+b64) exceeds "
            "safety budget of %d bytes (50%% of K8s Secret limit). "
            "With %d subclouds, redirect URIs may cause Helm release "
            "Secret to exceed 1 MiB." % (
                len(helm_secret_payload), overrides_budget, num_subclouds))

        # Also verify raw JSON stays reasonable (for readability in
        # helm-override-show and debugging)
        self.assertLess(
            len(overrides_json), k8s_secret_limit,
            "Raw override JSON (%d bytes) exceeds 1 MiB with %d "
            "subclouds." % (len(overrides_json), num_subclouds))


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
