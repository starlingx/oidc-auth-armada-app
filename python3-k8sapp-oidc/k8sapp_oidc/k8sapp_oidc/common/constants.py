#
# Copyright (c) 2020 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

# Helm: Supported charts:
# These values match the names in the chart package's Chart.yaml
HELM_CHART_DEX = 'dex'
HELM_CHART_OIDC_CLIENT = 'oidc-client'
HELM_CHART_SECRET_OBSERVER = 'secret-observer'  # nosec
# nosec to ignore bandit error of hard coded secret on previous line
