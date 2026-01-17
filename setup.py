# SPDX-License-Identifier: LGPL-3.0-or-later
from setuptools import setup, find_packages

setup(
    name="hyper2kvm",
    version="0.0.3",
    packages=find_packages(),
    install_requires=[l.strip() for l in open("requirements.txt", encoding="utf-8") if l.strip() and not l.startswith("#")],
    entry_points={"console_scripts": ["hyper2kvm=hyper2kvm.__main__:main"]},
)
