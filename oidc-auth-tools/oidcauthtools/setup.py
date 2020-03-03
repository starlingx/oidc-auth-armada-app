#!/usr/bin/env python
#
# Copyright (c) 2020 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#
import setuptools

setuptools.setup(
    install_requires=['python2-mechanize'],
    setup_requires=['pbr>=2.0.0'],
    pbr=True
)
