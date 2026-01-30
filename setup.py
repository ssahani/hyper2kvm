# SPDX-License-Identifier: LGPL-3.0-or-later
from setuptools import find_packages, setup

setup(
    name="hyper2kvm",
    version="0.0.3",
    packages=find_packages(),
    install_requires=[line.strip() for line in open("requirements.txt", encoding="utf-8") if line.strip() and not line.startswith("#")],
    entry_points={"console_scripts": ["hyper2kvm=hyper2kvm.__main__:main"]},
)
