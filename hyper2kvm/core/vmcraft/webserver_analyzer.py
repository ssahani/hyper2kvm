# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/core/vmcraft/webserver_analyzer.py
"""
Web server configuration analysis.

Provides comprehensive web server detection and analysis:
- Apache HTTP Server (httpd, apache2)
- Nginx
- Microsoft IIS
- Lighttpd
- Tomcat

Features:
- Detect installed web servers
- Parse configuration files
- List virtual hosts/server blocks
- Identify document roots
- SSL/TLS configuration
- Security settings
- Module/extension detection
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from .file_ops import FileOperations


class WebServerAnalyzer:
    """
    Web server configuration analyzer.

    Analyzes web server installations and configurations.
    """

    def __init__(self, logger: logging.Logger, file_ops: FileOperations, mount_root: Path):
        """
        Initialize web server analyzer.

        Args:
            logger: Logger instance
            file_ops: FileOperations instance
            mount_root: Root directory where guest filesystem is mounted
        """
        self.logger = logger
        self.file_ops = file_ops
        self.mount_root = mount_root

    def detect_webservers(self) -> dict[str, Any]:
        """
        Detect all web server installations.

        Returns:
            Web server detection results
        """
        webservers: dict[str, Any] = {
            "apache": None,
            "nginx": None,
            "iis": None,
            "lighttpd": None,
            "tomcat": None,
            "detected_count": 0,
        }

        # Detect Apache
        apache = self._detect_apache()
        if apache.get("installed"):
            webservers["apache"] = apache
            webservers["detected_count"] += 1

        # Detect Nginx
        nginx = self._detect_nginx()
        if nginx.get("installed"):
            webservers["nginx"] = nginx
            webservers["detected_count"] += 1

        # Detect IIS
        iis = self._detect_iis()
        if iis.get("installed"):
            webservers["iis"] = iis
            webservers["detected_count"] += 1

        # Detect Lighttpd
        lighttpd = self._detect_lighttpd()
        if lighttpd.get("installed"):
            webservers["lighttpd"] = lighttpd
            webservers["detected_count"] += 1

        # Detect Tomcat
        tomcat = self._detect_tomcat()
        if tomcat.get("installed"):
            webservers["tomcat"] = tomcat
            webservers["detected_count"] += 1

        return webservers

    def _detect_apache(self) -> dict[str, Any]:
        """Detect Apache HTTP Server."""
        apache: dict[str, Any] = {
            "installed": False,
            "version": None,
            "config_file": None,
            "document_root": None,
            "listen_ports": [],
            "virtual_hosts": [],
            "modules": [],
            "ssl_enabled": False,
        }

        # Check for Apache binary
        apache_paths = [
            "/usr/sbin/httpd",
            "/usr/sbin/apache2",
        ]

        for path in apache_paths:
            if self.file_ops.exists(path):
                apache["installed"] = True
                break

        if not apache["installed"]:
            return apache

        # Parse main configuration
        config_paths = [
            "/etc/httpd/conf/httpd.conf",
            "/etc/apache2/apache2.conf",
        ]

        for config_path in config_paths:
            if self.file_ops.exists(config_path):
                apache["config_file"] = config_path
                config = self._parse_apache_config(config_path)
                apache.update(config)
                break

        # Check for virtual hosts
        vhost_dirs = [
            "/etc/httpd/conf.d",
            "/etc/apache2/sites-enabled",
        ]

        for vhost_dir in vhost_dirs:
            if self.file_ops.is_dir(vhost_dir):
                vhosts = self._parse_apache_vhosts(vhost_dir)
                apache["virtual_hosts"].extend(vhosts)

        # Check for SSL
        if any("443" in str(port) for port in apache["listen_ports"]):
            apache["ssl_enabled"] = True

        return apache

    def _parse_apache_config(self, config_path: str) -> dict[str, Any]:
        """Parse Apache configuration file."""
        config: dict[str, Any] = {
            "listen_ports": [],
            "modules": [],
        }

        try:
            content = self.file_ops.cat(config_path)

            for line in content.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                # Listen directive
                if line.startswith("Listen"):
                    parts = line.split()
                    if len(parts) >= 2:
                        port = parts[1].split(":")[-1]  # Handle IP:port format
                        if port not in config["listen_ports"]:
                            config["listen_ports"].append(port)

                # DocumentRoot
                elif line.startswith("DocumentRoot"):
                    parts = line.split(None, 1)
                    if len(parts) >= 2:
                        config["document_root"] = parts[1].strip('"')

                # LoadModule
                elif line.startswith("LoadModule"):
                    parts = line.split()
                    if len(parts) >= 2:
                        module_name = parts[1]
                        config["modules"].append(module_name)

        except Exception as e:
            self.logger.debug(f"Failed to parse Apache config: {e}")

        return config

    def _parse_apache_vhosts(self, vhost_dir: str) -> list[dict[str, Any]]:
        """Parse Apache virtual host configurations."""
        vhosts = []

        try:
            vhost_files = self.file_ops.ls(vhost_dir)

            for vhost_file in vhost_files:
                if vhost_file.endswith(".conf"):
                    vhost_path = f"{vhost_dir}/{vhost_file}"
                    content = self.file_ops.cat(vhost_path)

                    vhost = {
                        "file": vhost_file,
                        "server_name": None,
                        "document_root": None,
                        "ssl": False,
                    }

                    for line in content.splitlines():
                        line = line.strip()

                        if line.startswith("ServerName"):
                            parts = line.split(None, 1)
                            if len(parts) >= 2:
                                vhost["server_name"] = parts[1]

                        elif line.startswith("DocumentRoot"):
                            parts = line.split(None, 1)
                            if len(parts) >= 2:
                                vhost["document_root"] = parts[1].strip('"')

                        elif "443" in line or "SSLEngine" in line:
                            vhost["ssl"] = True

                    if vhost["server_name"]:
                        vhosts.append(vhost)

        except Exception as e:
            self.logger.debug(f"Failed to parse Apache vhosts: {e}")

        return vhosts

    def _detect_nginx(self) -> dict[str, Any]:
        """Detect Nginx web server."""
        nginx: dict[str, Any] = {
            "installed": False,
            "version": None,
            "config_file": None,
            "listen_ports": [],
            "server_blocks": [],
            "ssl_enabled": False,
        }

        # Check for Nginx binary
        if self.file_ops.exists("/usr/sbin/nginx"):
            nginx["installed"] = True

        if not nginx["installed"]:
            return nginx

        # Parse main configuration
        config_path = "/etc/nginx/nginx.conf"
        if self.file_ops.exists(config_path):
            nginx["config_file"] = config_path

        # Check for server blocks
        sites_dirs = [
            "/etc/nginx/sites-enabled",
            "/etc/nginx/conf.d",
        ]

        for sites_dir in sites_dirs:
            if self.file_ops.is_dir(sites_dir):
                servers = self._parse_nginx_servers(sites_dir)
                nginx["server_blocks"].extend(servers)

        # Extract listen ports and SSL status
        for server in nginx["server_blocks"]:
            for port in server.get("listen_ports", []):
                if port not in nginx["listen_ports"]:
                    nginx["listen_ports"].append(port)
            if server.get("ssl"):
                nginx["ssl_enabled"] = True

        return nginx

    def _parse_nginx_servers(self, sites_dir: str) -> list[dict[str, Any]]:
        """Parse Nginx server blocks."""
        servers = []

        try:
            site_files = self.file_ops.ls(sites_dir)

            for site_file in site_files:
                if site_file.startswith("."):
                    continue

                site_path = f"{sites_dir}/{site_file}"
                if not self.file_ops.is_file(site_path):
                    continue

                content = self.file_ops.cat(site_path)

                server = {
                    "file": site_file,
                    "server_name": None,
                    "root": None,
                    "listen_ports": [],
                    "ssl": False,
                }

                for line in content.splitlines():
                    line = line.strip()

                    if line.startswith("listen"):
                        # Extract port from "listen 80;" or "listen 443 ssl;"
                        parts = line.split()
                        if len(parts) >= 2:
                            port = parts[1].rstrip(";")
                            server["listen_ports"].append(port)
                            if "ssl" in line:
                                server["ssl"] = True

                    elif line.startswith("server_name"):
                        parts = line.split(None, 1)
                        if len(parts) >= 2:
                            server["server_name"] = parts[1].rstrip(";")

                    elif line.startswith("root"):
                        parts = line.split(None, 1)
                        if len(parts) >= 2:
                            server["root"] = parts[1].rstrip(";")

                if server["server_name"]:
                    servers.append(server)

        except Exception as e:
            self.logger.debug(f"Failed to parse Nginx servers: {e}")

        return servers

    def _detect_iis(self) -> dict[str, Any]:
        """Detect Microsoft IIS (basic)."""
        iis: dict[str, Any] = {
            "installed": False,
            "version": None,
            "note": "IIS detection requires registry parsing",
        }

        # Check for IIS directories
        if self.file_ops.is_dir("/Windows/System32/inetsrv"):
            iis["installed"] = True

        return iis

    def _detect_lighttpd(self) -> dict[str, Any]:
        """Detect Lighttpd web server."""
        lighttpd: dict[str, Any] = {
            "installed": False,
            "config_file": None,
            "document_root": None,
            "port": None,
        }

        # Check for Lighttpd binary
        if self.file_ops.exists("/usr/sbin/lighttpd"):
            lighttpd["installed"] = True

        if not lighttpd["installed"]:
            return lighttpd

        # Parse configuration
        config_path = "/etc/lighttpd/lighttpd.conf"
        if self.file_ops.exists(config_path):
            lighttpd["config_file"] = config_path
            config = self._parse_lighttpd_config(config_path)
            lighttpd.update(config)

        return lighttpd

    def _parse_lighttpd_config(self, config_path: str) -> dict[str, Any]:
        """Parse Lighttpd configuration."""
        config = {}

        try:
            content = self.file_ops.cat(config_path)

            for line in content.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                if "=" in line:
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip().strip('"')

                    if key == "server.document-root":
                        config["document_root"] = value
                    elif key == "server.port":
                        config["port"] = value

        except Exception as e:
            self.logger.debug(f"Failed to parse Lighttpd config: {e}")

        return config

    def _detect_tomcat(self) -> dict[str, Any]:
        """Detect Apache Tomcat."""
        tomcat: dict[str, Any] = {
            "installed": False,
            "catalina_home": None,
            "version": None,
            "webapps": [],
        }

        # Check for Tomcat directories
        tomcat_paths = [
            "/usr/share/tomcat",
            "/opt/tomcat",
            "/var/lib/tomcat",
        ]

        for path in tomcat_paths:
            if self.file_ops.is_dir(path):
                tomcat["installed"] = True
                tomcat["catalina_home"] = path

                # List webapps
                webapps_dir = f"{path}/webapps"
                if self.file_ops.is_dir(webapps_dir):
                    webapps = self.file_ops.ls(webapps_dir)
                    tomcat["webapps"] = [w for w in webapps if not w.startswith(".")]

                break

        return tomcat

    def get_webserver_summary(self, webservers: dict[str, Any]) -> dict[str, Any]:
        """
        Get web server summary.

        Args:
            webservers: Web server detection results

        Returns:
            Summary dictionary
        """
        summary = {
            "total_webservers": webservers.get("detected_count", 0),
            "apache_installed": webservers.get("apache", {}).get("installed", False),
            "nginx_installed": webservers.get("nginx", {}).get("installed", False),
            "iis_installed": webservers.get("iis", {}).get("installed", False),
            "ssl_enabled": False,
        }

        # Check if any server has SSL enabled
        for server_name in ["apache", "nginx"]:
            server = webservers.get(server_name)
            if server and server.get("ssl_enabled"):
                summary["ssl_enabled"] = True
                break

        return summary

    def check_webserver_security(self, webservers: dict[str, Any]) -> list[dict[str, Any]]:
        """
        Check web server security settings.

        Args:
            webservers: Web server detection results

        Returns:
            List of security issues
        """
        issues = []

        # Check Apache
        apache = webservers.get("apache")
        if apache and apache.get("installed"):
            if not apache.get("ssl_enabled"):
                issues.append({
                    "server": "apache",
                    "severity": "medium",
                    "issue": "Apache not configured for SSL/TLS",
                    "recommendation": "Enable SSL/TLS for secure connections",
                })

            # Check for dangerous modules
            dangerous_modules = ["mod_autoindex", "mod_userdir"]
            for module in apache.get("modules", []):
                if any(dangerous in module for dangerous in dangerous_modules):
                    issues.append({
                        "server": "apache",
                        "severity": "low",
                        "issue": f"Potentially dangerous module enabled: {module}",
                        "recommendation": "Review module necessity",
                    })

        # Check Nginx
        nginx = webservers.get("nginx")
        if nginx and nginx.get("installed"):
            if not nginx.get("ssl_enabled"):
                issues.append({
                    "server": "nginx",
                    "severity": "medium",
                    "issue": "Nginx not configured for SSL/TLS",
                    "recommendation": "Enable SSL/TLS for secure connections",
                })

        return issues
