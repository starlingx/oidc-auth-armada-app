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

# Default local-LDAP Dex connector identity and userSearch attribute mappings.
DEFAULT_DEX_LDAP_CONNECTOR_ID = 'ldap-1'
DEFAULT_DEX_LDAP_BASE_DN = 'ou=People,dc=cgcs,dc=local'
DEFAULT_DEX_LDAP_BIND_DN = 'CN=ldapadmin,DC=cgcs,DC=local'
DEFAULT_DEX_GROUP_BASE_DN = 'ou=Group,dc=cgcs,dc=local'
DEFAULT_DEX_LDAP_USERNAME_ATTR = 'uid'
DEFAULT_DEX_LDAP_ID_ATTR = 'DN'
DEFAULT_DEX_LDAP_EMAIL_ATTR = 'mail'
DEFAULT_DEX_LDAP_NAME_ATTR = 'cn'
DEFAULT_DEX_LDAP_PREFERRED_USERNAME_ATTR = 'uid'
