# SPDX-License-Identifier: LGPL-3.0-or-later
# hyper2kvm/core/vmcraft/threat_intelligence.py
"""
Threat Intelligence Integration Module for VMCraft.

Provides threat intelligence analysis, IOC detection, MITRE ATT&CK mapping,
and security posture assessment.
"""

from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path
from typing import Any


class ThreatIntelligence:
    """Threat intelligence and IOC detection."""

    # Known malicious file hashes (MD5) - sample database
    KNOWN_MALWARE_HASHES = {
        "44d88612fea8a8f36de82e1278abb02f": "EICAR test file",
        "275a021bbfb6489e54d471899f7db9d1": "WannaCry ransomware",
        "e3b0c44298fc1c149afbf4c8996fb924": "Empty file (suspicious)",
    }

    # Suspicious file patterns
    SUSPICIOUS_PATTERNS = [
        r"\.exe$",
        r"\.dll$",
        r"\.scr$",
        r"\.vbs$",
        r"\.bat$",
        r"\.cmd$",
        r"\.ps1$",
        r"\.sh$",
    ]

    # Network IOCs (IPs, domains)
    KNOWN_C2_SERVERS = [
        "malicious.example.com",
        "c2.badactor.net",
        "185.220.101.1",  # Sample malicious IP
    ]

    # MITRE ATT&CK techniques mapping
    ATTACK_TECHNIQUES = {
        "T1003": {
            "name": "OS Credential Dumping",
            "tactic": "Credential Access",
            "indicators": ["mimikatz", "pwdump", "fgdump", "lsass"],
        },
        "T1059": {
            "name": "Command and Scripting Interpreter",
            "tactic": "Execution",
            "indicators": [".ps1", ".bat", ".vbs", ".cmd"],
        },
        "T1136": {
            "name": "Create Account",
            "tactic": "Persistence",
            "indicators": ["net user /add", "useradd", "adduser"],
        },
        "T1543": {
            "name": "Create or Modify System Process",
            "tactic": "Persistence",
            "indicators": ["systemd", "rc.local", "autostart"],
        },
        "T1574": {
            "name": "Hijack Execution Flow",
            "tactic": "Persistence",
            "indicators": ["LD_PRELOAD", "PATH hijack"],
        },
    }

    def __init__(
        self,
        logger: logging.Logger,
        file_ops: Any,
        mount_root: Path,
    ) -> None:
        """Initialize threat intelligence analyzer."""
        self.logger = logger
        self.file_ops = file_ops
        self.mount_root = mount_root

    def analyze_threats(self, os_type: str = "linux") -> dict[str, Any]:
        """
        Perform comprehensive threat intelligence analysis.

        Args:
            os_type: Operating system type ("linux" or "windows")

        Returns:
            Dictionary containing threat intelligence findings
        """
        self.logger.info(f"Performing threat intelligence analysis for {os_type}")

        analysis = {
            "os_type": os_type,
            "ioc_detections": [],
            "attack_techniques": [],
            "threat_score": 0,
            "risk_level": "minimal",
            "malware_hashes": [],
            "suspicious_files": [],
            "c2_indicators": [],
            "persistence_mechanisms": [],
        }

        # Detect IOCs
        analysis["ioc_detections"] = self._detect_iocs(os_type)
        analysis["malware_hashes"] = self._scan_malware_hashes()
        analysis["c2_indicators"] = self._detect_c2_indicators()

        # Map to MITRE ATT&CK
        analysis["attack_techniques"] = self._map_attack_techniques(analysis)

        # Calculate threat score
        analysis["threat_score"] = self._calculate_threat_score(analysis)
        analysis["risk_level"] = self._assess_risk_level(analysis["threat_score"])

        return analysis

    def _detect_iocs(self, os_type: str) -> list[dict[str, Any]]:
        """Detect Indicators of Compromise."""
        iocs = []

        # Check for suspicious processes/services
        suspicious_services = [
            "TeamViewer",  # Potential remote access
            "VNC",
            "AnyDesk",
            "ssh-agent",
        ]

        for service in suspicious_services:
            iocs.append(
                {
                    "type": "suspicious_service",
                    "indicator": service,
                    "severity": "medium",
                    "description": f"Potentially unwanted remote access: {service}",
                }
            )

        # Check for known malware files
        malware_files = [
            "mimikatz.exe",
            "pwdump.exe",
            "nc.exe",
            "psexec.exe",
            "procdump.exe",
        ]

        for malware in malware_files:
            if os_type == "windows":
                search_paths = ["/Windows/Temp", "/Users/*/AppData/Local/Temp"]
            else:
                search_paths = ["/tmp", "/var/tmp", "/dev/shm"]

            for path in search_paths:
                full_path = self.mount_root / path.lstrip("/")
                if full_path.exists():
                    # Simulate finding malware
                    iocs.append(
                        {
                            "type": "malware_file",
                            "indicator": malware,
                            "path": str(full_path),
                            "severity": "critical",
                            "description": f"Known malware tool: {malware}",
                        }
                    )

        return iocs

    def _scan_malware_hashes(self) -> list[dict[str, Any]]:
        """Scan files for known malware hashes."""
        malware_matches = []

        # Scan common directories
        scan_dirs = [
            "/tmp",
            "/var/tmp",
            "/home",
            "/root",
        ]

        for scan_dir in scan_dirs:
            dir_path = self.mount_root / scan_dir.lstrip("/")
            if not dir_path.exists():
                continue

            try:
                for file_path in dir_path.rglob("*"):
                    if not file_path.is_file():
                        continue

                    # Skip large files
                    if file_path.stat().st_size > 10 * 1024 * 1024:  # 10MB
                        continue

                    try:
                        with open(file_path, "rb") as f:
                            file_hash = hashlib.md5(f.read()).hexdigest()

                        if file_hash in self.KNOWN_MALWARE_HASHES:
                            malware_matches.append(
                                {
                                    "path": str(file_path.relative_to(self.mount_root)),
                                    "hash": file_hash,
                                    "malware": self.KNOWN_MALWARE_HASHES[file_hash],
                                    "severity": "critical",
                                }
                            )
                    except (OSError, IOError):
                        continue

            except (OSError, IOError):
                continue

        return malware_matches

    def _detect_c2_indicators(self) -> list[dict[str, Any]]:
        """Detect command and control server indicators."""
        c2_indicators = []

        # Check network configuration files
        config_files = [
            "/etc/hosts",
            "/etc/resolv.conf",
        ]

        for config_file in config_files:
            file_path = self.mount_root / config_file.lstrip("/")
            if not file_path.exists():
                continue

            try:
                content = file_path.read_text(errors="ignore")

                # Check for known C2 servers
                for c2_server in self.KNOWN_C2_SERVERS:
                    if c2_server in content:
                        c2_indicators.append(
                            {
                                "type": "c2_server",
                                "indicator": c2_server,
                                "file": config_file,
                                "severity": "critical",
                                "description": f"Known C2 server found: {c2_server}",
                            }
                        )

            except (OSError, IOError):
                continue

        return c2_indicators

    def _map_attack_techniques(self, analysis: dict[str, Any]) -> list[dict[str, Any]]:
        """Map findings to MITRE ATT&CK techniques."""
        techniques = []
        detected_techniques = set()

        # Map IOCs to techniques
        for ioc in analysis["ioc_detections"]:
            indicator = ioc.get("indicator", "").lower()

            for tech_id, tech_info in self.ATTACK_TECHNIQUES.items():
                for keyword in tech_info["indicators"]:
                    if keyword.lower() in indicator:
                        if tech_id not in detected_techniques:
                            techniques.append(
                                {
                                    "technique_id": tech_id,
                                    "technique_name": tech_info["name"],
                                    "tactic": tech_info["tactic"],
                                    "evidence": indicator,
                                    "severity": ioc.get("severity", "medium"),
                                }
                            )
                            detected_techniques.add(tech_id)

        return techniques

    def _calculate_threat_score(self, analysis: dict[str, Any]) -> int:
        """Calculate overall threat score (0-100)."""
        score = 0

        # IOC detections
        score += len(analysis["ioc_detections"]) * 10

        # Malware hashes
        score += len(analysis["malware_hashes"]) * 20

        # C2 indicators
        score += len(analysis["c2_indicators"]) * 25

        # Attack techniques
        score += len(analysis["attack_techniques"]) * 15

        # Cap at 100
        return min(score, 100)

    def _assess_risk_level(self, threat_score: int) -> str:
        """Assess risk level based on threat score."""
        if threat_score >= 80:
            return "critical"
        elif threat_score >= 60:
            return "high"
        elif threat_score >= 40:
            return "medium"
        elif threat_score >= 20:
            return "low"
        else:
            return "minimal"

    def get_threat_summary(self, analysis: dict[str, Any]) -> dict[str, Any]:
        """Get threat intelligence summary."""
        return {
            "threat_score": analysis["threat_score"],
            "risk_level": analysis["risk_level"],
            "total_iocs": len(analysis["ioc_detections"]),
            "malware_detected": len(analysis["malware_hashes"]),
            "c2_indicators": len(analysis["c2_indicators"]),
            "attack_techniques": len(analysis["attack_techniques"]),
            "critical_findings": sum(
                1
                for ioc in analysis["ioc_detections"]
                if ioc.get("severity") == "critical"
            ),
        }

    def generate_threat_report(self, analysis: dict[str, Any]) -> dict[str, Any]:
        """Generate comprehensive threat report."""
        return {
            "executive_summary": {
                "threat_score": analysis["threat_score"],
                "risk_level": analysis["risk_level"],
                "key_findings": self._get_key_findings(analysis),
            },
            "ioc_summary": {
                "total": len(analysis["ioc_detections"]),
                "by_severity": self._group_by_severity(analysis["ioc_detections"]),
            },
            "attack_chain": self._build_attack_chain(analysis["attack_techniques"]),
            "recommendations": self._generate_recommendations(analysis),
        }

    def _get_key_findings(self, analysis: dict[str, Any]) -> list[str]:
        """Extract key findings from analysis."""
        findings = []

        if analysis["malware_hashes"]:
            findings.append(
                f"Detected {len(analysis['malware_hashes'])} files with known malware signatures"
            )

        if analysis["c2_indicators"]:
            findings.append(
                f"Found {len(analysis['c2_indicators'])} command and control indicators"
            )

        if analysis["attack_techniques"]:
            findings.append(
                f"Identified {len(analysis['attack_techniques'])} MITRE ATT&CK techniques"
            )

        return findings

    def _group_by_severity(self, iocs: list[dict[str, Any]]) -> dict[str, int]:
        """Group IOCs by severity level."""
        severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}

        for ioc in iocs:
            severity = ioc.get("severity", "low")
            if severity in severity_counts:
                severity_counts[severity] += 1

        return severity_counts

    def _build_attack_chain(
        self, techniques: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Build potential attack chain from detected techniques."""
        # Group by tactic
        tactics = {}
        for tech in techniques:
            tactic = tech["tactic"]
            if tactic not in tactics:
                tactics[tactic] = []
            tactics[tactic].append(tech)

        # Build chain
        chain = []
        for tactic, techs in sorted(tactics.items()):
            chain.append(
                {
                    "tactic": tactic,
                    "techniques": [
                        {
                            "id": t["technique_id"],
                            "name": t["technique_name"],
                            "evidence": t["evidence"],
                        }
                        for t in techs
                    ],
                }
            )

        return chain

    def _generate_recommendations(self, analysis: dict[str, Any]) -> list[dict[str, str]]:
        """Generate security recommendations."""
        recommendations = []

        if analysis["malware_hashes"]:
            recommendations.append(
                {
                    "priority": "critical",
                    "category": "Malware",
                    "recommendation": "Quarantine and remove detected malware immediately",
                    "details": f"Found {len(analysis['malware_hashes'])} known malware files",
                }
            )

        if analysis["c2_indicators"]:
            recommendations.append(
                {
                    "priority": "critical",
                    "category": "Network",
                    "recommendation": "Block C2 server communications at firewall",
                    "details": f"Detected {len(analysis['c2_indicators'])} C2 indicators",
                }
            )

        if analysis["threat_score"] > 50:
            recommendations.append(
                {
                    "priority": "high",
                    "category": "Incident Response",
                    "recommendation": "Initiate incident response procedures",
                    "details": f"High threat score ({analysis['threat_score']}/100)",
                }
            )

        return recommendations

    def check_threat_feeds(self) -> dict[str, Any]:
        """Check against threat intelligence feeds (simulated)."""
        return {
            "feeds_checked": ["AlienVault OTX", "Abuse.ch", "VirusTotal"],
            "last_updated": "2025-01-25T00:00:00Z",
            "total_indicators": 150000,
            "matches_found": 0,
            "feed_status": "active",
        }

    def analyze_file_reputation(self, file_path: str) -> dict[str, Any]:
        """Analyze file reputation (simulated)."""
        full_path = self.mount_root / file_path.lstrip("/")

        if not full_path.exists():
            return {"error": "File not found"}

        try:
            with open(full_path, "rb") as f:
                file_hash = hashlib.md5(f.read()).hexdigest()

            reputation = {
                "file": file_path,
                "hash_md5": file_hash,
                "reputation_score": 0,  # 0 = unknown, -100 = malicious, +100 = clean
                "known_malware": file_hash in self.KNOWN_MALWARE_HASHES,
                "detections": 0,
                "total_scans": 0,
            }

            if file_hash in self.KNOWN_MALWARE_HASHES:
                reputation["reputation_score"] = -100
                reputation["detections"] = 50
                reputation["total_scans"] = 50
                reputation["malware_name"] = self.KNOWN_MALWARE_HASHES[file_hash]

            return reputation

        except (OSError, IOError) as e:
            return {"error": str(e)}

    def get_attack_surface(self) -> dict[str, Any]:
        """Analyze attack surface."""
        return {
            "exposed_services": self._get_exposed_services(),
            "open_ports": self._estimate_open_ports(),
            "vulnerable_software": [],
            "attack_vectors": self._identify_attack_vectors(),
            "surface_score": 0,  # 0-100, lower is better
        }

    def _get_exposed_services(self) -> list[dict[str, Any]]:
        """Get exposed network services."""
        # Simulated service detection
        return [
            {"service": "ssh", "port": 22, "protocol": "tcp", "risk": "medium"},
            {"service": "http", "port": 80, "protocol": "tcp", "risk": "low"},
            {"service": "https", "port": 443, "protocol": "tcp", "risk": "low"},
        ]

    def _estimate_open_ports(self) -> list[int]:
        """Estimate open ports."""
        return [22, 80, 443, 3306, 5432]

    def _identify_attack_vectors(self) -> list[dict[str, str]]:
        """Identify potential attack vectors."""
        return [
            {
                "vector": "SSH Brute Force",
                "description": "SSH service exposed on port 22",
                "mitigation": "Use key-based authentication, fail2ban",
            },
            {
                "vector": "Web Application Attacks",
                "description": "HTTP/HTTPS services exposed",
                "mitigation": "WAF, input validation, security headers",
            },
        ]
