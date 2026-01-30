#!/bin/bash
# Simple wrapper to run hyper2kvm from project directory
cd "$(dirname "$0")"
exec sudo python -m hyper2kvm "$@"
