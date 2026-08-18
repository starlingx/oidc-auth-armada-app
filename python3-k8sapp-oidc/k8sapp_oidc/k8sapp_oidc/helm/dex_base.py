#
# Copyright (c) 2020,2026 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

import json
import os
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import as_completed

from oslo_log import log as logging

from k8sapp_oidc.common import constants as app_constants

from sysinv.common import constants
from sysinv.common import rest_api

from sysinv.helm import base
from sysinv.helm import common

LOG = logging.getLogger(__name__)

# Map platform TLS version constants to Dex format ("1.2", "1.3")
DEX_TLS_VERSION_MAP = {
    constants.SERVICE_PARAM_PLATFORM_TLS_VERSION_TLS12: '1.2',
    constants.SERVICE_PARAM_PLATFORM_TLS_VERSION_TLS13: '1.3',
}

# Port used by the oidc-login kubectl plugin callback listener
OIDC_LOGIN_CALLBACK_PORT = 8000

# File tracking resolved subcloud OAM IPs from previous apply.
# Avoids re-querying all subclouds on every apply — only new
# subclouds (not present in this file) are queried.
# NOTE: /opt/platform is a DRBD-synced filesystem, so this file
# is available on both controllers after swact.
SUBCLOUD_OAM_LIST_FILE = '/opt/platform/.oidc_dc_subcloud_oam_list.json'

# Maximum concurrent requests to subcloud sysinv APIs
MAX_PARALLEL_SUBCLOUD_QUERIES = 50

# Timeout for individual subcloud sysinv API requests (seconds).
# Subclouds that fail to respond are skipped and retried on the
# next cron cycle (oidc-dc-sync runs every 15 minutes).
SUBCLOUD_QUERY_TIMEOUT = 10

# Sysinv API port
SYSINV_API_PORT = 6386


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


def get_subcloud_oam_floating_ips():
    """Retrieve OAM floating IPs for all managed subclouds.

    Uses a two-layer strategy for efficiency at scale (up to 5000
    subclouds):

    1. Query dcmanager list API for current managed subclouds,
       their management IPs, and their updated-at timestamps.
    2. Load the previously resolved subcloud OAM list from disk.
    3. Only query subclouds that are new or whose dcmanager record
       was updated since last resolution (detected via updated-at).
    4. Parallel-batch the queries to subcloud sysinv APIs.
    5. Persist the updated resolved list for next apply.

    Staleness detection: if a subcloud's OAM IP changes (reconfig),
    dcmanager's updated-at timestamp for that subcloud will advance
    (via audit or explicit update). On next oidc-auth-apps apply,
    the changed timestamp triggers a re-query of that subcloud's
    sysinv, picking up the new OAM IP automatically.

    The resolved list is stored at:
        /opt/platform/.oidc_dc_subcloud_oam_list.json

    :returns list: OAM floating IP strings for managed subclouds.
        Returns an empty list on any failure.
    """
    try:
        # Acquire token once in main thread — thread-safe for workers
        token = rest_api.get_token(constants.SYSTEM_CONTROLLER_REGION)
        if not token:
            LOG.warning("Failed to get token for subcloud OAM resolution")
            return []

        managed_subclouds = _get_managed_subclouds(token)
        if not managed_subclouds:
            return []

        # Load previously resolved OAM IPs
        known_subclouds = _load_subcloud_oam_list()

        # Determine which subclouds need querying:
        # - New subclouds (not in resolved list)
        # - Subclouds whose dcmanager record was updated since last
        #   resolution (updated_at advances on OAM reconfig, rehome,
        #   or any subcloud update — catches OAM IP changes)
        to_query = {}
        already_resolved = {}

        for sc_name, sc_info in managed_subclouds.items():
            known_entry = known_subclouds.get(sc_name)
            if (known_entry
                    and known_entry.get('oam_ip')
                    and known_entry.get('updated_at') == sc_info['updated_at']):
                already_resolved[sc_name] = known_entry['oam_ip']
            else:
                to_query[sc_name] = sc_info['mgmt_ip']

        # Query new/changed subclouds in parallel batches
        newly_resolved = {}
        if to_query:
            LOG.info("Querying %d subclouds for OAM IPs "
                     "(%d unchanged)", len(to_query),
                     len(already_resolved))
            newly_resolved = _batch_query_subcloud_oam_ips(token, to_query)

        # Build final OAM IP list and persist for next apply
        all_oam_ips = []
        updated_list = {}

        for sc_name, sc_info in managed_subclouds.items():
            oam_ip = (newly_resolved.get(sc_name)
                      or already_resolved.get(sc_name))

            if not oam_ip:
                # Subcloud failed to respond — keep previous OAM IP
                # if we had one, so we don't drop its redirect URI.
                # It will be re-queried on next apply (updated_at
                # still differs from what we store).
                prev_entry = known_subclouds.get(sc_name)
                if prev_entry:
                    oam_ip = prev_entry.get('oam_ip')

            if oam_ip:
                all_oam_ips.append(oam_ip)
                # Only update the stored timestamp if we successfully
                # resolved (or kept from unchanged). If we're using a
                # stale fallback, keep the OLD updated_at so next apply
                # will retry.
                stored_updated_at = sc_info['updated_at']
                if (sc_name in to_query
                        and sc_name not in newly_resolved
                        and sc_name in known_subclouds):
                    # Failed re-query — keep old timestamp to force retry
                    stored_updated_at = known_subclouds[sc_name].get(
                        'updated_at', '')

                updated_list[sc_name] = {
                    'mgmt_ip': sc_info['mgmt_ip'],
                    'oam_ip': oam_ip,
                    'updated_at': stored_updated_at,
                }

        # Save resolved list (prunes removed subclouds)
        _save_subcloud_oam_list(updated_list)

        failed_count = len(to_query) - len(newly_resolved)
        if failed_count > 0:
            LOG.warning("Failed to resolve OAM IP for %d subclouds "
                        "(unreachable or offline)", failed_count)

        LOG.info("Resolved %d subcloud OAM IPs for OIDC redirect URIs "
                 "(%d queried, %d unchanged)",
                 len(all_oam_ips), len(newly_resolved),
                 len(already_resolved))
        return all_oam_ips

    except Exception as e:
        LOG.warning("Failed to retrieve subcloud OAM IPs: %s", e)
        return []


def _get_managed_subclouds(token):
    """Query dcmanager for managed subclouds with their management IPs and timestamps.

    :param token: Keystone token for the SystemController region.
    :returns dict: {subcloud_name: {'mgmt_ip': str, 'updated_at': str}}
        for managed subclouds. Empty dict on failure.
    """
    try:
        api_url = token.get_service_url("dcmanager", "dcmanager")
        api_cmd = api_url + '/subclouds'
        api_cmd_headers = {
            'Content-type': 'application/json',
            'User-Agent': 'sysinv/1.0',
        }

        response = rest_api.rest_api_request(
            token, "GET", api_cmd, api_cmd_headers, timeout=30
        )

        if not response:
            return {}

        subclouds = response.get('subclouds', [])
        result = {}
        for sc in subclouds:
            if sc.get('management-state') == 'managed':
                name = sc.get('name')
                mgmt_ip = sc.get('management-start-ip')
                updated_at = sc.get('updated-at', '')
                if name and mgmt_ip:
                    result[name] = {
                        'mgmt_ip': mgmt_ip,
                        'updated_at': str(updated_at),
                    }

        return result

    except Exception as e:
        LOG.warning("Failed to query dcmanager for subclouds: %s", e)
        return {}


def _batch_query_subcloud_oam_ips(token, subclouds):
    """Query multiple subcloud sysinv APIs for OAM IPs in parallel.

    :param token: Keystone token (acquired in main thread, shared
        by all workers — thread-safe for read-only use).
    :param dict subclouds: {subcloud_name: management_start_ip}
    :returns dict: {subcloud_name: oam_floating_ip} for successful queries.
    """
    results = {}

    with ThreadPoolExecutor(
        max_workers=MAX_PARALLEL_SUBCLOUD_QUERIES
    ) as executor:
        futures = {
            executor.submit(
                _query_subcloud_oam_ip, token, name, mgmt_ip
            ): name
            for name, mgmt_ip in subclouds.items()
        }

        for future in as_completed(futures):
            sc_name = futures[future]
            try:
                oam_ip = future.result()
                if oam_ip:
                    results[sc_name] = oam_ip
            except Exception as e:
                LOG.debug("Failed to get OAM IP for subcloud %s: %s",
                          sc_name, e)

    return results


def _query_subcloud_oam_ip(token, subcloud_name, mgmt_ip):
    """Query a single subcloud's sysinv API for its OAM floating IP.

    Uses the pre-acquired system controller token to authenticate
    against the subcloud's sysinv endpoint.

    :param token: Pre-acquired Keystone token (thread-safe for reads).
    :param str subcloud_name: Subcloud name (for logging).
    :param str mgmt_ip: Management start IP of the subcloud.
    :returns str: OAM floating IP, or None on failure.
    """
    try:
        # Format IPv6 addresses with brackets
        if ':' in mgmt_ip:
            host = '[%s]' % mgmt_ip
        else:
            host = mgmt_ip

        api_cmd = 'https://%s:%d/v1/iextoam' % (host, SYSINV_API_PORT)

        api_cmd_headers = {
            'Content-type': 'application/json',
            'User-Agent': 'sysinv/1.0',
        }

        response = rest_api.rest_api_request(
            token, "GET", api_cmd, api_cmd_headers,
            timeout=SUBCLOUD_QUERY_TIMEOUT
        )

        if not response:
            return None

        # Response is a dict with 'iextoams' list
        oam_list = response.get('iextoams', [])
        if oam_list and len(oam_list) > 0:
            return oam_list[0].get('oam_floating_ip')

        return None

    except Exception as e:
        LOG.debug("Error querying OAM for subcloud %s (%s): %s",
                  subcloud_name, mgmt_ip, e)
        return None


def _load_subcloud_oam_list():
    """Load previously resolved subcloud OAM IPs from disk.

    :returns dict:
        {subcloud_name: {'mgmt_ip': str, 'oam_ip': str, 'updated_at': str}}
    """
    try:
        if os.path.isfile(SUBCLOUD_OAM_LIST_FILE):
            with open(SUBCLOUD_OAM_LIST_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        LOG.debug("Failed to load subcloud OAM list: %s", e)

    return {}


def _save_subcloud_oam_list(subcloud_oam_data):
    """Persist resolved subcloud OAM IPs to disk.

    Only managed subclouds are written — removed subclouds are
    automatically pruned.

    :param dict subcloud_oam_data:
        {subcloud_name: {'mgmt_ip': str, 'oam_ip': str, 'updated_at': str}}
    """
    try:
        tmp_path = SUBCLOUD_OAM_LIST_FILE + '.tmp'
        with open(tmp_path, 'w') as f:
            json.dump(subcloud_oam_data, f, indent=2)
        os.chmod(tmp_path, 0o640)
        os.rename(tmp_path, SUBCLOUD_OAM_LIST_FILE)
    except Exception as e:
        LOG.debug("Failed to save subcloud OAM list: %s", e)
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


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
    # Port for oauth2-proxy callback (routed via HAProxy on Keystone port)
    OAUTH2_PROXY_PORT = 5000

    @property
    def CHART(self):
        # subclasses must define the property: CHART='name of chart'
        # if an author of a new chart forgets this, NotImplementedError is raised
        raise NotImplementedError

    def get_namespaces(self):
        return self.SUPPORTED_NAMESPACES

    def _get_client_id(self):
        return app_constants.DEFAULT_OIDC_CLIENT_ID

    def _get_client_secret(self):
        return app_constants.DEFAULT_OIDC_CLIENT_SECRET

    def _get_platform_tls_config(self):
        """Read TLS min version and cipher suite from platform service parameters.

        Returns a tuple of (tls_min_version, tls_cipher_suite) using
        platform defaults if the parameters are not configured.
        """
        return get_platform_tls_config(self.dbapi)
