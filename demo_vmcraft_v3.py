#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-3.0-or-later
"""
VMCraft v3.0 - Feature Demonstration

Shows how to use the new v3.0 enterprise features.
Note: This is a demonstration script showing API usage.
To run against a real VM, provide a disk image path.
"""

from hyper2kvm.core.vmcraft import VMCraft


def demo_network_analysis():
    """Demonstrate network configuration analysis."""
    print("\n" + "=" * 70)
    print("Network Configuration Analysis")
    print("=" * 70)

    print("""
Example usage:

    with VMCraft() as g:
        g.add_drive_opts("disk.qcow2", readonly=True)
        g.launch()

        # Analyze network configuration
        network = g.analyze_network_config(os_type="linux")
        print(f"Network manager: {network['network_manager']}")
        print(f"Hostname: {network['hostname']}")
        print(f"DNS servers: {network['dns_servers']}")
        print(f"Interfaces: {len(network['interfaces'])}")

        # Find static IPs
        static_ips = g.find_static_ips(network)
        print(f"Static IPs: {static_ips}")

        # Detect network bonding
        bonds = g.detect_network_bonds(network)
        print(f"Bonded interfaces: {len(bonds)}")

Supported network managers:
  • NetworkManager (/etc/NetworkManager/system-connections/)
  • systemd-networkd (/etc/systemd/network/)
  • ifcfg (/etc/sysconfig/network-scripts/)
  • netplan (/etc/netplan/)
  • interfaces (/etc/network/interfaces)
""")


def demo_firewall_analysis():
    """Demonstrate firewall analysis."""
    print("\n" + "=" * 70)
    print("Firewall Analysis")
    print("=" * 70)

    print("""
Example usage:

    with VMCraft() as g:
        g.add_drive_opts("disk.qcow2", readonly=True)
        g.launch()

        # Analyze firewall
        firewall = g.analyze_firewall(os_type="linux")
        print(f"Firewall type: {firewall['firewall_type']}")
        print(f"Enabled: {firewall['enabled']}")

        # Get open ports
        open_ports = g.get_open_ports(firewall)
        print(f"Open ports: {open_ports}")

        # Get blocked ports
        blocked_ports = g.get_blocked_ports(firewall)
        print(f"Blocked ports: {blocked_ports}")

        # Get statistics
        stats = g.get_firewall_stats(firewall)
        print(f"Total rules: {stats['total_rules']}")
        print(f"Open ports: {stats['open_ports_count']}")
        print(f"Blocked ports: {stats['blocked_ports_count']}")

Supported firewalls:
  • iptables (rules.v4, /etc/sysconfig/iptables)
  • firewalld (/etc/firewalld/)
  • ufw (/etc/ufw/)
  • nftables (/etc/nftables.conf)
""")


def demo_ssh_security():
    """Demonstrate SSH security analysis."""
    print("\n" + "=" * 70)
    print("SSH Security Analysis")
    print("=" * 70)

    print("""
Example usage:

    with VMCraft() as g:
        g.add_drive_opts("disk.qcow2", readonly=True)
        g.launch()

        # Analyze SSH configuration
        ssh = g.analyze_ssh_config()

        # Check security score
        score = g.get_security_score(ssh)
        print(f"SSH Security Score: {score['score']} ({score['grade']})")
        print(f"Critical issues: {score['critical_issues']}")
        print(f"High issues: {score['high_issues']}")
        print(f"Medium issues: {score['medium_issues']}")
        print(f"Low issues: {score['low_issues']}")

        # Check specific settings
        print(f"SSH port: {g.get_ssh_port(ssh)}")
        print(f"Root login allowed: {g.is_root_login_allowed(ssh)}")
        print(f"Password auth enabled: {g.is_password_auth_enabled(ssh)}")
        print(f"Authorized keys: {g.get_authorized_key_count(ssh)}")

        # Security issues
        for issue in ssh['security_issues']:
            print(f"[{issue['severity'].upper()}] {issue['issue']}")
            print(f"  Recommendation: {issue['recommendation']}")

Security grading:
  A (90-100): Excellent security
  B (80-89):  Good security
  C (70-79):  Acceptable security
  D (60-69):  Poor security
  F (0-59):   Critical security issues
""")


def demo_scheduled_tasks():
    """Demonstrate scheduled task analysis."""
    print("\n" + "=" * 70)
    print("Scheduled Task Analysis")
    print("=" * 70)

    print("""
Example usage:

    with VMCraft() as g:
        g.add_drive_opts("disk.qcow2", readonly=True)
        g.launch()

        # Analyze scheduled tasks
        tasks = g.analyze_scheduled_tasks(os_type="linux")
        print(f"Total tasks: {g.get_task_count(tasks)}")
        print(f"System cron: {len(tasks['system_cron'])}")
        print(f"User cron: {len(tasks['user_cron'])}")
        print(f"Systemd timers: {len(tasks['systemd_timers'])}")

        # Find daily tasks
        daily = g.find_daily_tasks(tasks)
        print(f"Daily tasks: {len(daily)}")
        for task in daily[:5]:
            print(f"  - {task['schedule']}: {task['command']}")

        # Find root's tasks
        root_tasks = g.find_tasks_by_user(tasks, "root")
        print(f"Root's tasks: {len(root_tasks)}")

Supported schedulers:
  • cron (/etc/crontab, /etc/cron.d/*, /var/spool/cron/*)
  • systemd timers (/etc/systemd/system/*.timer)
  • anacron (/etc/anacrontab)
  • Windows Task Scheduler
""")


def demo_log_analysis():
    """Demonstrate log analysis."""
    print("\n" + "=" * 70)
    print("Log Analysis")
    print("=" * 70)

    print("""
Example usage:

    with VMCraft() as g:
        g.add_drive_opts("disk.qcow2", readonly=True)
        g.launch()

        # Comprehensive log analysis
        logs = g.analyze_logs()
        stats = logs['statistics']

        print(f"Total errors: {stats['total_errors']}")
        print(f"Total warnings: {stats['total_warnings']}")
        print(f"Failed logins: {stats['failed_logins']}")
        print(f"Successful logins: {stats['successful_logins']}")
        print(f"Sudo usage: {stats['sudo_usage']}")

        # Get recent errors
        errors = g.get_recent_errors(hours=24, limit=10)
        for error in errors[:5]:
            print(f"ERROR: {error.get('message', error.get('raw'))}")

        # Get critical events
        critical = g.get_critical_events()
        for event in critical:
            print(f"CRITICAL: {event.get('message', event.get('raw'))}")

Analyzed logs:
  • System: syslog, messages, dmesg
  • Auth: auth.log, secure
  • Apps: Apache, Nginx, MySQL, PostgreSQL
  • Security: Failed logins, sudo usage
""")


def demo_hardware_detection():
    """Demonstrate hardware detection."""
    print("\n" + "=" * 70)
    print("Hardware Detection")
    print("=" * 70)

    print("""
Example usage:

    with VMCraft() as g:
        g.add_drive_opts("disk.qcow2", readonly=True)
        g.launch()

        # Detect hardware
        hardware = g.detect_hardware()

        # Check if virtual machine
        if g.is_virtual_machine(hardware):
            hypervisor = g.get_hypervisor(hardware)
            print(f"Running on: {hypervisor}")

        # Get detailed info
        summary = g.get_hardware_summary(hardware)
        print(f"Manufacturer: {summary['manufacturer']}")
        print(f"Product: {summary['product']}")
        print(f"CPU: {summary['cpu_model']}")
        print(f"Cores: {summary['cpu_cores']}")
        print(f"Disks: {summary['disk_count']}")
        print(f"NICs: {summary['network_interfaces']}")

        # Individual queries
        memory_mb = g.get_total_memory_mb(hardware)
        disk_count = g.get_disk_count(hardware)
        nic_count = g.get_network_interface_count(hardware)

Detected hypervisors:
  • VMware (ESXi, Workstation, Fusion)
  • KVM/QEMU
  • Microsoft Hyper-V
  • Oracle VirtualBox
  • Xen
""")


def demo_comprehensive_audit():
    """Demonstrate comprehensive VM audit."""
    print("\n" + "=" * 70)
    print("Comprehensive VM Security Audit")
    print("=" * 70)

    print("""
Complete security audit example:

    from hyper2kvm.core.vmcraft import VMCraft

    with VMCraft() as g:
        g.add_drive_opts("vm_disk.qcow2", readonly=True)
        g.launch()

        # Detect OS
        roots = g.inspect_os()
        root = roots[0]
        os_type = g.inspect_get_type(root)

        # Collect comprehensive data
        audit_data = {
            'os': {
                'type': os_type,
                'product': g.inspect_get_product_name(root),
                'version': f"{g.inspect_get_major_version(root)}.{g.inspect_get_minor_version(root)}",
            },
            'network': g.analyze_network_config(os_type),
            'firewall': g.analyze_firewall(os_type),
            'ssh': g.analyze_ssh_config(),
            'tasks': g.analyze_scheduled_tasks(os_type),
            'logs': g.analyze_logs(),
            'hardware': g.detect_hardware(),
        }

        # Security scoring
        ssh_score = g.get_security_score(audit_data['ssh'])

        # Export report
        g.export_json(audit_data, 'vm_audit.json')
        g.export_yaml(audit_data, 'vm_audit.yaml')
        g.export_markdown_report(audit_data, 'vm_audit.md',
                                  title='VM Security Audit Report')

        print(f"✓ Audit complete - SSH score: {ssh_score['grade']}")
        print(f"✓ Reports exported to: vm_audit.json, vm_audit.yaml, vm_audit.md")
""")


def main():
    """Run all demonstrations."""
    print("\n" + "=" * 70)
    print("VMCraft v3.0 - Feature Demonstration")
    print("=" * 70)
    print("""
This script demonstrates the new enterprise-grade features in VMCraft v3.0.

New v3.0 Features:
  • Network configuration analysis (3 methods)
  • Firewall rule analysis (4 methods)
  • SSH security auditing (6 methods)
  • Scheduled task inventory (4 methods)
  • System log analysis (3 methods)
  • Hardware detection (7 methods)

Total: 27 new methods across 6 modules
""")

    demo_network_analysis()
    demo_firewall_analysis()
    demo_ssh_security()
    demo_scheduled_tasks()
    demo_log_analysis()
    demo_hardware_detection()
    demo_comprehensive_audit()

    print("\n" + "=" * 70)
    print("For real usage, provide a VM disk image:")
    print("  with VMCraft() as g:")
    print("      g.add_drive_opts('/path/to/disk.qcow2', readonly=True)")
    print("      g.launch()")
    print("      # ... use any of the methods shown above")
    print("=" * 70)
    print()


if __name__ == '__main__':
    main()
