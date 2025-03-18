#!/usr/bin/python3

#
# Copyright (c) 2020-2023 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

from argparse import ArgumentParser
import getpass
import mechanize
import os
import re
import six
import ssl
import sys
import urllib


def main():

    parser = ArgumentParser(description="OIDC authentication")

    # The alias "oamcontroller" is present in "/etc/hosts" and points to the
    # controller OAM floating address.
    parser.add_argument("-c", "--client", dest="client",
                        help="OIDC client IP address (default: controller "
                        "floating OAM IP)", default="oamcontroller")
    parser.add_argument("-u", "--username", dest="username",
                        help="Username (default: current logged in username)")
    parser.add_argument("-p", "--password", dest="password",
                        help="Password. Prompted if not present.")
    parser.add_argument("-b", "--backend", dest="backend",
                        help="Dex configured backend name")
    parser.add_argument("-ca", "--cacert", dest="cacert",
                        help="Path to ca certificate file",
                        default=None)

    parser.add_argument("-v", "--verbose", action='count')
    args = parser.parse_args()

    verbose = args.verbose
    username = args.username
    password = args.password
    client = args.client
    cacert = args.cacert

    if not username:
        try:
            username = getpass.getuser()
        # Unclear which exception(s) to expect.
        except Exception as error:
            print('ERROR', error)
            sys.exit(1)
        print('Using "' + username + '" as username.')

    if not password:
        try:
            password = getpass.getpass()
        except Exception as error:
            print('ERROR', error)
            sys.exit(1)

    dexClientUrl = "https://" + client + ":30555"
    if verbose:
        print("client: " + dexClientUrl)
        print("username: " + username)
        print("password: " + password)

    default_cacert = None
    OS_CACERT = os.environ.get('OS_CACERT', None)
    if OS_CACERT:
        default_cacert = os.path.join(os.getcwd(), OS_CACERT)

    # prioritize the cacert informed by the user, otherwise use the OS_CACERT
    cafile = None
    if cacert:
        if os.path.exists(cacert):
            cafile = cacert
            if verbose:
                print(f"Using given cafile: {cafile}")
        else:
            print(f"ERROR: The provided cacert file: {cacert} was not found")
            sys.exit(1)

    if cafile is None and default_cacert:
        if os.path.exists(default_cacert):
            cafile = default_cacert
            if verbose:
                print(f"Using certificate provided at OS_CACERT: {OS_CACERT}")
        else:
            print(f"WARN: The OS_CACERT set to {OS_CACERT} but was not found")

    br = mechanize.Browser()
    if cafile:
        br.set_ca_data(context=ssl.create_default_context(
            cafile=cafile))
    else:
        if verbose:
            print("WARN: No valid cerfiticate found, using unverified context")
        br.set_ca_data(context=ssl._create_unverified_context(
            cert_reqs=ssl.CERT_NONE))
    br.set_handle_robots(False)
    br.addheaders = [("User-agent", "Mozilla/5.0")]

    # Open browser on dexClientUrl
    try:
        dexLoginPage = br.open(dexClientUrl)
    except urllib.error.URLError as e:
        if e.reason:
            print("Error")
            print(f"- Reason: {e.reason}")
            error_code = re.search(r"\d+", str(e.reason))
            if error_code:
                ecode = int(error_code.group())
                print(f"- Code: {ecode}")
                if ecode == 111:
                    print("- Check oidc-auth-apps application pod status")
                elif ecode == 113:
                    print("- Check OIDC client IP address parameter (-c)")
                elif ecode == 110:
                    print("- Connection timeout")
                else:
                    print("- Unexpected Error addressing the OIDC Client")
            else:
                print("- Unexpected HTTP Error: "
                      "failed to parse response code")
                print('- Check oidc-auth-apps configuration on the controller')
        sys.exit(1)
    except Exception as e:
        print(f'Unexpected Error from mechanize.Browser.open(): {e}')
        sys.exit(1)

    # If there are links on this page, then more than one
    # backends are configured. Pick the correct backend
    if len(br.links()) > 0:
        if not args.backend:
            print("Multiple backends detected, please select one with -b")
            sys.exit(1)

        found_backend = False
        all_backends = []
        for link in br.links():
            if not link.text.startswith("Log in with "):
                print("Error reading backend: %s" % link.text)

            all_backends.append(link.text[len("Log in with "):])
            if verbose:
                print("backend: %s" % all_backends[-1])

            if all_backends[-1] == args.backend:
                try:
                    br.follow_link(link)
                    found_backend = True
                except mechanize.LinkNotFoundError:
                    print(f'Error: The backend link: {link} was not found')
                except mechanize.HTTPError as e:
                    print(f'HTTP Error {e.code}:failed following link: {link}')
                except Exception as e:
                    print('Unexpected Error from '
                          f'mechanize.Browser.follow_link(): {e}')

        if not found_backend:
            print("Backend not found, please choose one of: %s" % all_backends)
            sys.exit(1)

    # NOW ON DEX LOGIN PAGE
    if verbose:
        print("\ndexLoginPage:")
        print("--------------")
        print(dexLoginPage.read())

        print("\ndexLoginPage FORMS:")
        print("-----------------")
        for form in br.forms():
            print("Form name: ", form.name)
            print(form)

        print("\ndexLoginPage FORM CONTROLS:")
        print("--------------------------")

    br.form = list(br.forms())[0]

    if verbose:
        for control in br.form.controls:
            print("Control name / type: ", control.name, " / ", control.type)
            print(control)

    br["login"] = username
    br["password"] = password

    if verbose:
        print("\ndexLoginPage SUBMITTING FORM --> ...")
    try:
        dexLoginGrantAccessResponse = br.submit()
    except mechanize.HTTPError as e:
        if e.code == 500:
            # handles mis-configuration of baseND for example
            # handles DNS lookup failure for example
            print('Dex server replied with HTTP error code 500.\n'
                  'Review the dex server pod log and configuration '
                  'to resolve the error.')
        elif e.code == 401:
            print('Failed to authenticate - check username/password')
        else:
            print('Unexpected error returned from the dex server; '
                  'check pod status and logs')
        print('Error: %s' % e)
        sys.exit(1)
    except Exception as e:
        print(f'Unexpected Error from mechanize.Browser.submit(): {e}')
        sys.exit(1)

    # grant access final response
    if verbose:
        print("\ndexLoginGrantAccessResponse:")
        print("------------------")

    stringResponse = dexLoginGrantAccessResponse.read()
    # stringResponse is bytes type. In python3 bytes and str are different.
    # Convert it to str so the following string operations will succeed.
    if six.PY3:
        stringResponse = stringResponse.decode()

    if verbose:
        print(stringResponse)

    idTokenLine = ""
    for item in stringResponse.split("\n"):
        if 'ID Token' in item:
            idTokenLine = item.strip()

    if not idTokenLine:
        print("Login failed.")
        sys.exit(1)

    idToken = ""
    import xml.etree.ElementTree as ET
    tree = ET.fromstring(idTokenLine)
    for node in tree.iter('code'):
        print("Login succeeded.")
        idToken = node.text

    print("Updating kubectl config ...")
    updateCredsCmd = ("kubectl config set-credentials " +
                      username + " --token " + idToken)

    os.system(updateCredsCmd)


if __name__ == "__main__":
    ret = main()
    sys.exit(ret)
