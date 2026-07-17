#
# Copyright (c) 2026 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#
"""Shared test constants for oidc-auth-armada-app tests."""

OAM_IP_V4 = "10.10.10.2"
OAM_IP_V6 = "fd01::2"
MGMT_IP_V4 = "192.168.204.2"
MGMT_IP_V6 = "fd00::2"
LDAP_PASSWORD = "testpassword123"
ISSUER_URL_V4 = "https://10.10.10.2:30556/dex"
ISSUER_URL_V6 = "https://[fd01::2]:30556/dex"
DEX_NODE_PORT = 30556
OIDC_CLIENT_NODE_PORT = 30555
OAUTH2_PROXY_PORT = 5000
APP_NAME = "oidc-auth-apps"
CHART_DEX = "dex"
CHART_OIDC_CLIENT = "oidc-client"
CHART_SECRET_OBSERVER = "secret-observer"
KUBE_SYSTEM_NS = "kube-system"
