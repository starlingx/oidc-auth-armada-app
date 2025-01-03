#
# Copyright (c) 2024 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#
# All Rights Reserved.
#

""" System inventory App lifecycle operator."""

from k8sapp_oidc.common import constants as app_constants
from oslo_log import log as logging
from sysinv.common import constants
from sysinv.helm import lifecycle_base as base
from sysinv.helm import common
from sysinv.helm.lifecycle_constants import LifecycleConstants
from sysinv.db import api as dbapi


LOG = logging.getLogger(__name__)
OVERRIDES_REQUIRED_MSG = "Overrides for all helm charts are required to apply \
OIDC. Refer to 'Set up OIDC Auth Applications' guide to configure the \
application"


class OidcAppLifecycleOperator(base.AppLifecycleOperator):
    def app_lifecycle_actions(self, context, conductor_obj, app_op, app,
                              hook_info):

        """Perform lifecycle actions for an operation"""

        if hook_info.lifecycle_type == LifecycleConstants.APP_LIFECYCLE_TYPE_RESOURCE:
            if hook_info.operation == constants.APP_APPLY_OP and \
               hook_info.relative_timing == LifecycleConstants.APP_LIFECYCLE_TIMING_PRE:
                return self.pre_apply(app_op, app, hook_info)

        super(OidcAppLifecycleOperator, self).app_lifecycle_actions(
            context, conductor_obj, app_op, app, hook_info)

    def pre_apply(self, app_op, app, hook_info):
        """
        Pre Apply action

        Search for required overrides before apply the application. If at least
        one of the mandatory overrides doesn't exists, raise an 'apply-failed'
        status in the application-list informing the user about the required
        overrides.
        """
        dbapi_instance = dbapi.get_instance()
        db_app = dbapi_instance.kube_app_get(constants.HELM_APP_OIDC_AUTH)

        for helm_chart in [app_constants.HELM_CHART_OIDC_CLIENT,
                           app_constants.HELM_CHART_DEX,
                           app_constants.HELM_CHART_SECRET_OBSERVER]:

            helm_override = dbapi_instance.helm_override_get(
                app_id=db_app.id,
                name=helm_chart,
                namespace=common.HELM_NS_KUBE_SYSTEM)

            if helm_override.user_overrides is None:
                raise Exception(OVERRIDES_REQUIRED_MSG)
