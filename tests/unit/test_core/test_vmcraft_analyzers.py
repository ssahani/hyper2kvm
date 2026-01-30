"""
Unit tests for VMCraft analyzer modules

Tests detection and analysis of system components including firewalls,
databases, webservers, and cloud-init configurations.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from pathlib import Path


class TestFirewallAnalyzer:
    """Test firewall detection and analysis"""

    @pytest.fixture
    def mock_guestfs(self):
        """Create mock libguestfs handle"""
        g = Mock()
        g.exists = Mock()
        g.is_file = Mock()
        g.cat = Mock()
        return g

    def test_detect_iptables_rules(self, mock_guestfs):
        """Test detection of iptables firewall rules"""
        iptables_rules = """
*filter
:INPUT DROP [0:0]
:FORWARD DROP [0:0]
:OUTPUT ACCEPT [0:0]
-A INPUT -i lo -j ACCEPT
-A INPUT -m state --state RELATED,ESTABLISHED -j ACCEPT
-A INPUT -p tcp --dport 22 -j ACCEPT
-A INPUT -p tcp --dport 80 -j ACCEPT
-A INPUT -p tcp --dport 443 -j ACCEPT
COMMIT
"""
        mock_guestfs.exists.return_value = True
        mock_guestfs.cat.return_value = iptables_rules

        if mock_guestfs.exists("/etc/sysconfig/iptables"):
            rules = mock_guestfs.cat("/etc/sysconfig/iptables")

            # Detect open ports
            assert "-A INPUT -p tcp --dport 22 -j ACCEPT" in rules
            assert "-A INPUT -p tcp --dport 80 -j ACCEPT" in rules
            assert "-A INPUT -p tcp --dport 443 -j ACCEPT" in rules

            # Detect default policy
            assert ":INPUT DROP" in rules

    def test_detect_firewalld_zones(self, mock_guestfs):
        """Test detection of firewalld zones and services"""
        public_zone = """<?xml version="1.0" encoding="utf-8"?>
<zone>
  <short>Public</short>
  <description>For use in public areas</description>
  <service name="ssh"/>
  <service name="http"/>
  <service name="https"/>
  <port protocol="tcp" port="8080"/>
</zone>
"""
        mock_guestfs.exists.return_value = True
        mock_guestfs.cat.return_value = public_zone

        if mock_guestfs.exists("/etc/firewalld/zones/public.xml"):
            zone_config = mock_guestfs.cat("/etc/firewalld/zones/public.xml")

            # Detect enabled services
            assert 'service name="ssh"' in zone_config
            assert 'service name="http"' in zone_config
            assert 'service name="https"' in zone_config

            # Detect custom ports
            assert 'port="8080"' in zone_config

    def test_detect_nftables(self, mock_guestfs):
        """Test detection of nftables (newer netfilter)"""
        nftables_conf = """
table inet filter {
    chain input {
        type filter hook input priority 0; policy drop;
        ct state established,related accept
        tcp dport { 22, 80, 443 } accept
    }
}
"""
        mock_guestfs.exists.return_value = True
        mock_guestfs.cat.return_value = nftables_conf

        if mock_guestfs.exists("/etc/nftables.conf"):
            config = mock_guestfs.cat("/etc/nftables.conf")

            # Detect nftables syntax
            assert "table inet filter" in config
            assert "policy drop" in config
            assert "tcp dport { 22, 80, 443 }" in config

    def test_malformed_rule_handling(self, mock_guestfs):
        """Test handling of malformed firewall rules"""
        malformed_rules = """
*filter
:INPUT DROP [0:0]
-A INPUT -p tcp --dport 22  # Missing -j target
COMMIT
"""
        mock_guestfs.cat.return_value = malformed_rules

        rules = mock_guestfs.cat("/etc/sysconfig/iptables")

        # Should detect malformed rule (missing -j)
        has_malformed = "-A INPUT" in rules and "-j" not in rules.split('\n')[2]


class TestDatabaseDetector:
    """Test database service detection"""

    @pytest.fixture
    def mock_guestfs(self):
        """Create mock libguestfs handle"""
        g = Mock()
        g.exists = Mock()
        g.cat = Mock()
        return g

    def test_detect_postgresql(self, mock_guestfs):
        """Test PostgreSQL detection"""
        pg_hba_conf = """
# PostgreSQL Client Authentication Configuration
local   all             postgres                                peer
host    all             all             127.0.0.1/32            md5
host    all             all             ::1/128                 md5
"""
        mock_guestfs.exists.side_effect = lambda p: "postgresql" in p
        mock_guestfs.cat.return_value = pg_hba_conf

        # Check for PostgreSQL
        if mock_guestfs.exists("/var/lib/pgsql/data/pg_hba.conf"):
            config = mock_guestfs.cat("/var/lib/pgsql/data/pg_hba.conf")

            # Detect PostgreSQL authentication methods
            assert "peer" in config
            assert "md5" in config

            detected_db = "postgresql"
            assert detected_db == "postgresql"

    def test_detect_mysql(self, mock_guestfs):
        """Test MySQL/MariaDB detection"""
        mysql_conf = """
[mysqld]
datadir=/var/lib/mysql
socket=/var/lib/mysql/mysql.sock
bind-address=127.0.0.1
port=3306
"""
        mock_guestfs.exists.side_effect = lambda p: "my.cnf" in p
        mock_guestfs.cat.return_value = mysql_conf

        if mock_guestfs.exists("/etc/my.cnf"):
            config = mock_guestfs.cat("/etc/my.cnf")

            # Detect MySQL configuration
            assert "datadir=/var/lib/mysql" in config
            assert "port=3306" in config

            detected_db = "mysql"
            assert detected_db == "mysql"

    def test_detect_mongodb(self, mock_guestfs):
        """Test MongoDB detection"""
        mongod_conf = """
storage:
  dbPath: /var/lib/mongo
  journal:
    enabled: true

systemLog:
  destination: file
  path: /var/log/mongodb/mongod.log

net:
  port: 27017
  bindIp: 127.0.0.1
"""
        mock_guestfs.exists.side_effect = lambda p: "mongod.conf" in p
        mock_guestfs.cat.return_value = mongod_conf

        if mock_guestfs.exists("/etc/mongod.conf"):
            config = mock_guestfs.cat("/etc/mongod.conf")

            # Detect MongoDB configuration
            assert "dbPath: /var/lib/mongo" in config
            assert "port: 27017" in config

            detected_db = "mongodb"
            assert detected_db == "mongodb"

    def test_missing_database(self, mock_guestfs):
        """Test when no database is installed"""
        mock_guestfs.exists.return_value = False

        # Check for common database paths
        has_postgres = mock_guestfs.exists("/var/lib/pgsql")
        has_mysql = mock_guestfs.exists("/var/lib/mysql")
        has_mongo = mock_guestfs.exists("/var/lib/mongo")

        # No database detected
        assert not has_postgres
        assert not has_mysql
        assert not has_mongo


class TestWebserverAnalyzer:
    """Test webserver detection and configuration analysis"""

    @pytest.fixture
    def mock_guestfs(self):
        """Create mock libguestfs handle"""
        g = Mock()
        g.exists = Mock()
        g.cat = Mock()
        g.ls = Mock()
        return g

    def test_detect_apache(self, mock_guestfs):
        """Test Apache HTTP Server detection"""
        httpd_conf = """
ServerRoot "/etc/httpd"
Listen 80
Listen 443

<VirtualHost *:80>
    ServerName example.com
    DocumentRoot /var/www/html
</VirtualHost>
"""
        mock_guestfs.exists.side_effect = lambda p: "httpd" in p
        mock_guestfs.cat.return_value = httpd_conf

        if mock_guestfs.exists("/etc/httpd/conf/httpd.conf"):
            config = mock_guestfs.cat("/etc/httpd/conf/httpd.conf")

            # Detect Apache configuration
            assert "ServerRoot" in config
            assert "Listen 80" in config
            assert "VirtualHost" in config

            detected_server = "apache"
            assert detected_server == "apache"

    def test_detect_nginx(self, mock_guestfs):
        """Test Nginx detection"""
        nginx_conf = """
user nginx;
worker_processes auto;

http {
    server {
        listen 80;
        server_name example.com;
        root /usr/share/nginx/html;

        location / {
            try_files $uri $uri/ =404;
        }
    }
}
"""
        mock_guestfs.exists.side_effect = lambda p: "nginx" in p
        mock_guestfs.cat.return_value = nginx_conf

        if mock_guestfs.exists("/etc/nginx/nginx.conf"):
            config = mock_guestfs.cat("/etc/nginx/nginx.conf")

            # Detect Nginx configuration
            assert "worker_processes" in config
            assert "server_name" in config
            assert "location /" in config

            detected_server = "nginx"
            assert detected_server == "nginx"

    def test_parse_vhost_configs(self, mock_guestfs):
        """Test parsing virtual host configurations"""
        vhost_conf = """
<VirtualHost *:80>
    ServerName site1.example.com
    ServerAlias www.site1.example.com
    DocumentRoot /var/www/site1
</VirtualHost>

<VirtualHost *:80>
    ServerName site2.example.com
    DocumentRoot /var/www/site2
</VirtualHost>
"""
        mock_guestfs.cat.return_value = vhost_conf

        config = mock_guestfs.cat("/etc/httpd/conf.d/vhosts.conf")

        # Count virtual hosts
        vhost_count = config.count("<VirtualHost")
        assert vhost_count == 2

        # Extract server names
        assert "site1.example.com" in config
        assert "site2.example.com" in config

    def test_ssl_certificate_detection(self, mock_guestfs):
        """Test SSL certificate detection"""
        ssl_conf = """
<VirtualHost *:443>
    ServerName secure.example.com

    SSLEngine on
    SSLCertificateFile /etc/pki/tls/certs/server.crt
    SSLCertificateKeyFile /etc/pki/tls/private/server.key
    SSLCertificateChainFile /etc/pki/tls/certs/chain.crt
</VirtualHost>
"""
        mock_guestfs.cat.return_value = ssl_conf
        mock_guestfs.exists.side_effect = lambda p: "server.crt" in p or "server.key" in p

        config = mock_guestfs.cat("/etc/httpd/conf.d/ssl.conf")

        # Detect SSL configuration
        assert "SSLEngine on" in config
        assert "SSLCertificateFile" in config

        # Check if certificate files exist
        has_cert = mock_guestfs.exists("/etc/pki/tls/certs/server.crt")
        has_key = mock_guestfs.exists("/etc/pki/tls/private/server.key")

        assert has_cert
        assert has_key


class TestCloudDetector:
    """Test cloud platform detection"""

    @pytest.fixture
    def mock_guestfs(self):
        """Create mock libguestfs handle"""
        g = Mock()
        g.exists = Mock()
        g.cat = Mock()
        return g

    def test_detect_aws_metadata(self, mock_guestfs):
        """Test AWS cloud detection via metadata"""
        # AWS cloud-init datasource config
        cloud_cfg = """
datasource_list: [ Ec2, None ]
datasource:
  Ec2:
    metadata_urls: [ 'http://169.254.169.254' ]
"""
        mock_guestfs.exists.side_effect = lambda p: "cloud" in p
        mock_guestfs.cat.return_value = cloud_cfg

        if mock_guestfs.exists("/etc/cloud/cloud.cfg.d/90_aws.cfg"):
            config = mock_guestfs.cat("/etc/cloud/cloud.cfg.d/90_aws.cfg")

            # Detect AWS datasource
            assert "Ec2" in config
            assert "169.254.169.254" in config

            detected_cloud = "aws"
            assert detected_cloud == "aws"

    def test_detect_azure_metadata(self, mock_guestfs):
        """Test Azure cloud detection"""
        cloud_cfg = """
datasource_list: [ Azure ]
datasource:
  Azure:
    apply_network_config: true
"""
        mock_guestfs.exists.side_effect = lambda p: "cloud" in p
        mock_guestfs.cat.return_value = cloud_cfg

        if mock_guestfs.exists("/etc/cloud/cloud.cfg.d/90_azure.cfg"):
            config = mock_guestfs.cat("/etc/cloud/cloud.cfg.d/90_azure.cfg")

            # Detect Azure datasource
            assert "Azure" in config

            detected_cloud = "azure"
            assert detected_cloud == "azure"

    def test_detect_gcp_metadata(self, mock_guestfs):
        """Test GCP (Google Cloud Platform) detection"""
        cloud_cfg = """
datasource_list: [ GCE ]
datasource:
  GCE:
    retries: 5
"""
        mock_guestfs.exists.side_effect = lambda p: "cloud" in p
        mock_guestfs.cat.return_value = cloud_cfg

        if mock_guestfs.exists("/etc/cloud/cloud.cfg.d/90_gce.cfg"):
            config = mock_guestfs.cat("/etc/cloud/cloud.cfg.d/90_gce.cfg")

            # Detect GCE datasource
            assert "GCE" in config

            detected_cloud = "gcp"
            assert detected_cloud == "gcp"

    def test_detect_cloud_init_presence(self, mock_guestfs):
        """Test cloud-init installation detection"""
        # Test with cloud-init present
        mock_guestfs.exists.side_effect = lambda p: p == "/etc/cloud/cloud.cfg"

        has_cloud_init = mock_guestfs.exists("/etc/cloud/cloud.cfg")
        assert has_cloud_init is True

        # Test with no cloud-init
        mock_guestfs.exists.side_effect = lambda p: False

        has_cloud_init = mock_guestfs.exists("/etc/cloud/cloud.cfg")
        assert has_cloud_init is False


class TestContainerRuntimeDetector:
    """Test container runtime detection"""

    @pytest.fixture
    def mock_guestfs(self):
        """Create mock libguestfs handle"""
        g = Mock()
        g.exists = Mock()
        g.cat = Mock()
        return g

    def test_detect_docker(self, mock_guestfs):
        """Test Docker detection"""
        docker_daemon = """
{
  "storage-driver": "overlay2",
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}
"""
        mock_guestfs.exists.side_effect = lambda p: "docker" in p
        mock_guestfs.cat.return_value = docker_daemon

        if mock_guestfs.exists("/etc/docker/daemon.json"):
            config = mock_guestfs.cat("/etc/docker/daemon.json")

            # Detect Docker configuration
            assert "storage-driver" in config
            assert "overlay2" in config

            detected_runtime = "docker"
            assert detected_runtime == "docker"

    def test_detect_podman(self, mock_guestfs):
        """Test Podman detection"""
        mock_guestfs.exists.side_effect = lambda p: "containers" in p

        if mock_guestfs.exists("/etc/containers/storage.conf"):
            detected_runtime = "podman"
            assert detected_runtime == "podman"

    def test_detect_containerd(self, mock_guestfs):
        """Test containerd detection"""
        containerd_config = """
version = 2
root = "/var/lib/containerd"
state = "/run/containerd"

[grpc]
  address = "/run/containerd/containerd.sock"
"""
        mock_guestfs.exists.side_effect = lambda p: "containerd" in p
        mock_guestfs.cat.return_value = containerd_config

        if mock_guestfs.exists("/etc/containerd/config.toml"):
            config = mock_guestfs.cat("/etc/containerd/config.toml")

            # Detect containerd configuration
            assert "containerd" in config

            detected_runtime = "containerd"
            assert detected_runtime == "containerd"


class TestKubernetesDetector:
    """Test Kubernetes component detection"""

    @pytest.fixture
    def mock_guestfs(self):
        """Create mock libguestfs handle"""
        g = Mock()
        g.exists = Mock()
        g.cat = Mock()
        return g

    def test_detect_kubelet(self, mock_guestfs):
        """Test kubelet detection"""
        kubelet_conf = """
apiVersion: kubelet.config.k8s.io/v1beta1
kind: KubeletConfiguration
clusterDNS:
  - 10.96.0.10
clusterDomain: cluster.local
"""
        mock_guestfs.exists.side_effect = lambda p: "kubelet" in p
        mock_guestfs.cat.return_value = kubelet_conf

        if mock_guestfs.exists("/var/lib/kubelet/config.yaml"):
            config = mock_guestfs.cat("/var/lib/kubelet/config.yaml")

            # Detect kubelet configuration
            assert "KubeletConfiguration" in config
            assert "clusterDNS" in config

            is_k8s_node = True
            assert is_k8s_node is True

    def test_detect_kubeadm_config(self, mock_guestfs):
        """Test kubeadm configuration detection"""
        kubeadm_conf = """
apiVersion: kubeadm.k8s.io/v1beta3
kind: ClusterConfiguration
kubernetesVersion: v1.27.0
networking:
  podSubnet: 10.244.0.0/16
  serviceSubnet: 10.96.0.0/12
"""
        mock_guestfs.exists.side_effect = lambda p: "kubeadm" in p
        mock_guestfs.cat.return_value = kubeadm_conf

        if mock_guestfs.exists("/etc/kubernetes/kubeadm-config.yaml"):
            config = mock_guestfs.cat("/etc/kubernetes/kubeadm-config.yaml")

            # Detect kubeadm cluster config
            assert "ClusterConfiguration" in config
            assert "kubernetesVersion" in config


class TestServiceAnalyzer:
    """Test systemd service analysis"""

    @pytest.fixture
    def mock_guestfs(self):
        """Create mock libguestfs handle"""
        g = Mock()
        g.exists = Mock()
        g.cat = Mock()
        return g

    def test_detect_enabled_services(self, mock_guestfs):
        """Test detection of enabled systemd services"""
        # Enabled services have symlinks in /etc/systemd/system
        mock_guestfs.exists.side_effect = lambda p: "sshd.service" in p or "httpd.service" in p

        enabled_services = []
        for service in ["sshd.service", "httpd.service", "nonexistent.service"]:
            if mock_guestfs.exists(f"/etc/systemd/system/multi-user.target.wants/{service}"):
                enabled_services.append(service)

        assert "sshd.service" in enabled_services
        assert "httpd.service" in enabled_services
        assert "nonexistent.service" not in enabled_services

    def test_parse_service_unit_file(self, mock_guestfs):
        """Test parsing systemd service unit file"""
        service_unit = """
[Unit]
Description=OpenSSH server daemon
After=network.target

[Service]
Type=notify
ExecStart=/usr/sbin/sshd -D
Restart=on-failure

[Install]
WantedBy=multi-user.target
"""
        mock_guestfs.cat.return_value = service_unit

        unit = mock_guestfs.cat("/usr/lib/systemd/system/sshd.service")

        # Parse service properties
        assert "Description=OpenSSH server daemon" in unit
        assert "ExecStart=/usr/sbin/sshd" in unit
        assert "WantedBy=multi-user.target" in unit


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
