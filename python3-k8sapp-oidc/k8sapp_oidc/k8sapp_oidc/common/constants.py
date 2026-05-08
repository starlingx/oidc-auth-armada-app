#
# Copyright (c) 2020-2026 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

# Helm: Supported charts:
# These values match the names in the chart package's Chart.yaml
HELM_CHART_DEX = 'dex'
HELM_CHART_OIDC_CLIENT = 'oidc-client'
HELM_CHART_SECRET_OBSERVER = 'secret-observer'  # nosec
# nosec to ignore bandit error of hard coded secret on previous line

# File where OIDC login parameters are dumped for kubeconfig-setup
OIDC_LOGIN_CONFIG_FILE = '/opt/platform/.oidc_login_config'

# Default OIDC client credentials
DEFAULT_OIDC_CLIENT_ID = 'stx-oidc-client-app'
DEFAULT_OIDC_CLIENT_SECRET = 'St8rlingX'  # nosec
