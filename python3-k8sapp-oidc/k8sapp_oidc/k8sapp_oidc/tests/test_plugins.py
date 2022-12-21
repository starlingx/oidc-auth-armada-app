#
# Copyright (c) 2020 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

from sysinv.common import constants
from sysinv.tests.db import base as dbbase
from sysinv.tests.helm.test_helm import HelmOperatorTestSuiteMixin


class K8SAppOidcAppMixin(object):
    app_name = constants.HELM_APP_OIDC_AUTH
    path_name = app_name + '.tgz'

    def setUp(self):
        super(K8SAppOidcAppMixin, self).setUp()


# Test Configuration:
    # - Controller
    # - IPv6
    # - Ceph Storage
    # - oidc-auth-apps app
class K8SAppOidcControllerTestCase(K8SAppOidcAppMixin,
                                   dbbase.BaseIPv6Mixin,
                                   dbbase.BaseCephStorageBackendMixin,
                                   HelmOperatorTestSuiteMixin,
                                   dbbase.ControllerHostTestCase):
    pass


# Test Configuration:
# - AIO
# - IPv4
# - Ceph Storage
# - oidc-auth-apps app
class K8SAppOidcAIOTestCase(K8SAppOidcAppMixin,
                            dbbase.BaseCephStorageBackendMixin,
                            HelmOperatorTestSuiteMixin,
                            dbbase.AIOSimplexHostTestCase):
    pass
