#
# Copyright (c) 2020 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#
#!/usr/bin/env python

import getopt, sys
import getpass
from argparse import ArgumentParser
import mechanize
import ssl

def main():

    parser = ArgumentParser(description="OIDC authentication")

    parser.add_argument("-c", "--client", dest="client",
                        help="OIDC client IP address",
                        required=True)
    parser.add_argument("-u", "--username", dest="username",
                        help="Username",
                        required=True)
    parser.add_argument("-p", "--password", dest="password",
                        help="Password")

    parser.add_argument("-v", "--verbose", action='count')
    args = parser.parse_args()

    verbose = args.verbose
    username = args.username
    password = args.password
    client = args.client

    if not password:
        try:
            password = getpass.getpass()
        except Exception as error:
            print('ERROR', error)

    dexClientUrl = "https://" + client + ":30555"
    if verbose:
        print ("client: " + dexClientUrl)
        print ("username: " + username)
        print ("password: " + password)

    ssl._create_default_https_context = ssl._create_unverified_context
    br = mechanize.Browser()
    br.set_handle_robots(False)
    br.addheaders = [("User-agent","Mozilla/5.0")]

    # Open browser on dexClientUrl
    dexLoginPage = br.open(dexClientUrl)

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
    dexLoginGrantAccessResponse = br.submit()

    # grant access final response
    if verbose:
        print("\ndexLoginGrantAccessResponse:")
        print("------------------")

    stringResponse = dexLoginGrantAccessResponse.read()
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
    updateCredsCmd = "kubectl config set-credentials " + username + " --token " + idToken

    import os
    result = os.system(updateCredsCmd)


if __name__ == "__main__":
    ret = main()
    sys.exit(ret)
