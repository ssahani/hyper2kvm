Name:           hyper2kvm
Version:        0.0.1
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

Requires:       python3-rich >= 13.0.0
Requires:       python3-click >= 8.0.0
Requires:       python3-pyyaml >= 6.0
Requires:       python3-requests >= 2.31.0
Requires:       python3-pyvmomi >= 8.0.0
Requires:       libguestfs-tools
Requires:       qemu-img

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

%check
# Basic import test
%{__python3} -c "import hyper2kvm; print(hyper2kvm.__version__)"

# Verify command is available
%{buildroot}%{_bindir}/hyper2kvm --version

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
%{_docdir}/%{name}/

%changelog
* Wed Jan 15 2026 Susant Sahani <ssahani@redhat.com> - 3.1.0-1
- Initial RPM package
- Add comprehensive man pages
- Include example configurations
- Support for VMware vSphere, Hyper-V, and Azure migrations
