Name:           hyper2kvm
Version:        0.0.2
Release:        1%{?dist}
Summary:        Production-grade hypervisor to KVM/QEMU migration toolkit

License:        LGPL-3.0-or-later
URL:            https://github.com/hyper2kvm/hyper2kvm
Source0:        %{name}-%{version}.tar.gz

BuildArch:      noarch

BuildRequires:  python3-devel
BuildRequires:  python3-setuptools
BuildRequires:  python3-pip
BuildRequires:  python3-wheel
BuildRequires:  python3-build
BuildRequires:  python3-sphinx
BuildRequires:  python3-sphinx_rtd_theme
BuildRequires:  make
BuildRequires:  systemd-rpm-macros

Requires:       python3-rich >= 13.0.0
Requires:       python3-click >= 8.0.0
Requires:       python3-pyyaml >= 6.0
Requires:       python3-requests >= 2.31.0
Requires:       python3-pyvmomi >= 8.0.0
Requires:       libguestfs-tools
Requires:       qemu-img
Requires:       systemd

Requires(pre):    shadow-utils
Requires(post):   systemd
Requires(preun):  systemd
Requires(postun): systemd

# Optional but recommended dependencies
Recommends:     virt-v2v
Recommends:     nbdkit
Recommends:     libvirt-client
Recommends:     qemu-kvm

%description
hyper2kvm is a comprehensive toolkit for migrating virtual machines from
multiple hypervisors and disk ecosystems (VMware vSphere, Hyper-V, Azure,
AWS, local disks) into reliable, bootable KVM/QEMU systems.

The tool handles the complete migration pipeline:
- FETCH: Download or access source VM disks from various hypervisors
- FLATTEN: Consolidate snapshot chains and differencing disks
- INSPECT: Analyze guest OS, bootloader, and filesystem configuration
- FIX: Repair boot configuration, regenerate initramfs, stabilize device paths
- CONVERT: Transform disk formats (VMDK/VHD/VHDx → QCOW2/RAW)
- VALIDATE: Test boot and verify functionality

Features:
- Multi-platform support (VMware, Hyper-V, Azure, local disks)
- Automated guest OS fixes (bootloader, initramfs, fstab)
- Windows VirtIO driver injection
- Post-migration validation
- Zero-downtime migration support
- Batch processing capabilities

%prep
%autosetup -p1

%build
# Build Python package
%{python3} -m build --wheel --no-isolation

# Build man pages
cd man
%{__python3} -m sphinx -b man source build/man
cd ..

%install
# Install Python package
%{python3} -m pip install --no-index --no-deps --root %{buildroot} --prefix %{_prefix} --no-build-isolation dist/*.whl

# Install man pages
install -d %{buildroot}%{_mandir}/man1
install -d %{buildroot}%{_mandir}/man5
install -m 644 man/build/man/hyper2kvm.1 %{buildroot}%{_mandir}/man1/
install -m 644 man/build/man/hyper2kvm-local.1 %{buildroot}%{_mandir}/man1/
install -m 644 man/build/man/hyper2kvm-vsphere.1 %{buildroot}%{_mandir}/man1/
install -m 644 man/build/man/hyper2kvm-hyperv.1 %{buildroot}%{_mandir}/man1/
install -m 644 man/build/man/hyper2kvm-azure.1 %{buildroot}%{_mandir}/man1/
install -m 644 man/build/man/hyper2kvm.conf.5 %{buildroot}%{_mandir}/man5/

# Install example configurations
install -d %{buildroot}%{_docdir}/%{name}/examples
install -m 644 test-confs/*.yaml %{buildroot}%{_docdir}/%{name}/examples/
install -m 644 test-confs/*.json %{buildroot}%{_docdir}/%{name}/examples/

# Install documentation
install -d %{buildroot}%{_docdir}/%{name}
install -m 644 README.md %{buildroot}%{_docdir}/%{name}/
install -m 644 INSTALLATION.md %{buildroot}%{_docdir}/%{name}/
install -m 644 DEPENDENCIES.md %{buildroot}%{_docdir}/%{name}/
cp -r docs/* %{buildroot}%{_docdir}/%{name}/

# Install systemd service files
install -d %{buildroot}%{_unitdir}
install -m 644 systemd/hyper2kvm.service %{buildroot}%{_unitdir}/
install -m 644 systemd/hyper2kvm@.service %{buildroot}%{_unitdir}/

# Install systemd documentation
install -d %{buildroot}%{_docdir}/%{name}/systemd
install -m 644 systemd/README.md %{buildroot}%{_docdir}/%{name}/systemd/

# Create directories for daemon mode
install -d %{buildroot}%{_sharedstatedir}/%{name}
install -d %{buildroot}%{_localstatedir}/log/%{name}
install -d %{buildroot}%{_sysconfdir}/%{name}

%check
# Basic import test
%{__python3} -c "import hyper2kvm; print(hyper2kvm.__version__)"

# Verify command is available
%{buildroot}%{_bindir}/hyper2kvm --version

%pre
# Create hyper2kvm system user and group
getent group hyper2kvm >/dev/null || groupadd -r hyper2kvm
getent passwd hyper2kvm >/dev/null || \
    useradd -r -g hyper2kvm -d %{_sharedstatedir}/%{name} -s /sbin/nologin \
    -c "hyper2kvm daemon user" hyper2kvm
exit 0

%post
%systemd_post hyper2kvm.service hyper2kvm@.service

# Add hyper2kvm user to necessary groups for libguestfs, QEMU, and libvirt access
# Only add to groups that exist on the system
for group in qemu kvm libvirt disk; do
    if getent group "$group" >/dev/null 2>&1; then
        usermod -a -G "$group" hyper2kvm >/dev/null 2>&1 || :
    fi
done

# Set ownership of working directories
if [ $1 -eq 1 ]; then
    # Initial installation
    chown hyper2kvm:hyper2kvm %{_sharedstatedir}/%{name}
    chown hyper2kvm:hyper2kvm %{_localstatedir}/log/%{name}
    chown root:hyper2kvm %{_sysconfdir}/%{name}
    chmod 750 %{_sysconfdir}/%{name}
fi

%preun
%systemd_preun hyper2kvm.service hyper2kvm@.service

%postun
%systemd_postun_with_restart hyper2kvm.service hyper2kvm@.service

# Remove user on final uninstall
if [ $1 -eq 0 ]; then
    userdel hyper2kvm 2>/dev/null || :
    groupdel hyper2kvm 2>/dev/null || :
fi

%files
%license LICENSE
%doc README.md INSTALLATION.md DEPENDENCIES.md
%{_bindir}/hyper2kvm
%{python3_sitelib}/hyper2kvm/
%{python3_sitelib}/hyper2kvm-*.egg-info/
%{_mandir}/man1/hyper2kvm.1*
%{_mandir}/man1/hyper2kvm-local.1*
%{_mandir}/man1/hyper2kvm-vsphere.1*
%{_mandir}/man1/hyper2kvm-hyperv.1*
%{_mandir}/man1/hyper2kvm-azure.1*
%{_mandir}/man5/hyper2kvm.conf.5*
%{_unitdir}/hyper2kvm.service
%{_unitdir}/hyper2kvm@.service
%dir %attr(0750,hyper2kvm,hyper2kvm) %{_sharedstatedir}/%{name}
%dir %attr(0750,hyper2kvm,hyper2kvm) %{_localstatedir}/log/%{name}
%dir %attr(0750,root,hyper2kvm) %{_sysconfdir}/%{name}
%{_docdir}/%{name}/

%changelog
* Wed Jan 15 2026 Susant Sahani <ssahani@redhat.com> - 0.0.1-1
- Initial RPM package
- Add comprehensive man pages
- Include example configurations
- Support for VMware vSphere, Hyper-V, and Azure migrations
- Add systemd service units for daemon mode
- Create system user and directories for daemon operation
- Add hyper2kvm user to qemu, kvm, libvirt, and disk groups for proper access
