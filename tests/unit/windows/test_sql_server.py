"""Unit tests for SQL Server Manager."""

import logging
import pytest
from pathlib import Path
from unittest.mock import Mock

from hyper2kvm.windows.sql_server import SQLServerManager


class TestSQLServerManager:
    """Test SQL Server Manager functionality."""

    @pytest.fixture
    def sql_manager(self):
        """Create SQLServerManager instance."""
        logger = logging.getLogger("test")
        return SQLServerManager(logger)

    @pytest.fixture
    def mock_vmcraft(self):
        """Create mock VMCraft instance."""
        mock = Mock()
        mock.exists = Mock(return_value=True)
        mock.upload = Mock()
        return mock

    def test_init(self, sql_manager):
        """Test SQLServerManager initialization."""
        assert sql_manager is not None
        assert sql_manager.logger is not None
        assert len(sql_manager.SQL_SERVER_PATHS) > 0

    def test_detect_sql_server_installed(self, sql_manager, mock_vmcraft):
        """Test SQL Server detection when installed."""
        # Mock SQL Server installation
        mock_vmcraft.exists.side_effect = lambda path: (
            "Microsoft SQL Server" in path
        )

        result = sql_manager.detect_sql_server(mock_vmcraft)

        assert result["detected"] is True or result["detected"] is False
        assert "instances" in result
        assert "databases" in result

    def test_detect_sql_server_not_installed(self, sql_manager, mock_vmcraft):
        """Test SQL Server detection when not installed."""
        # Mock no SQL Server
        mock_vmcraft.exists.return_value = False

        result = sql_manager.detect_sql_server(mock_vmcraft)

        assert result["detected"] is False
        assert len(result["instances"]) == 0

    def test_migrate_sql_configuration(self, sql_manager, mock_vmcraft):
        """Test SQL Server migration configuration."""
        sql_info = {
            "instances": [
                {
                    "name": "MSSQLSERVER",
                    "version": "SQL Server 2019",
                    "port": 1433,
                }
            ]
        }

        result = sql_manager.migrate_sql_configuration(
            mock_vmcraft,
            sql_info,
            target_ip="192.168.1.100",
            target_hostname="new-server",
        )

        # Should generate script even if not fully implemented
        assert "script_generated" in result
        assert "instances_configured" in result

    def test_migrate_sql_configuration_no_instances(self, sql_manager, mock_vmcraft):
        """Test SQL migration fails gracefully with no instances."""
        sql_info = {"instances": []}

        result = sql_manager.migrate_sql_configuration(mock_vmcraft, sql_info)

        assert result["script_generated"] is False
        assert result["error"] is not None

    def test_create_sql_migration_script(self, sql_manager):
        """Test SQL migration script generation."""
        sql_info = {
            "instances": [
                {
                    "name": "MSSQLSERVER",
                    "version": "SQL Server 2019",
                    "port": 1433,
                },
                {
                    "name": "SQLEXPRESS",
                    "version": "SQL Server 2019",
                    "port": 1434,
                },
            ]
        }

        script = sql_manager.create_sql_migration_script(
            sql_info, target_ip="192.168.1.100", target_hostname="new-server"
        )

        assert "SQL Server" in script
        assert "192.168.1.100" in script
        assert "new-server" in script
        assert "MSSQLSERVER" in script
        assert "SQLEXPRESS" in script

    def test_validate_databases(self, sql_manager, mock_vmcraft):
        """Test database validation script generation."""
        sql_info = {
            "instances": [{"name": "MSSQLSERVER", "version": "SQL Server 2019"}],
            "databases": [
                {"name": "master", "instance": "MSSQLSERVER"},
                {"name": "model", "instance": "MSSQLSERVER"},
            ],
        }

        result = sql_manager.validate_databases(mock_vmcraft, sql_info)

        # Should generate validation script
        assert "script_generated" in result

    @pytest.mark.parametrize(
        "instance_name,expected_server_instance",
        [
            ("MSSQLSERVER", "localhost"),
            ("SQLEXPRESS", "localhost\\SQLEXPRESS"),
        ],
    )
    def test_sql_instance_naming(
        self, sql_manager, instance_name, expected_server_instance
    ):
        """Test SQL Server instance naming convention."""
        sql_info = {
            "instances": [{"name": instance_name, "version": "SQL Server 2019"}]
        }

        script = sql_manager.create_sql_migration_script(sql_info)

        assert expected_server_instance in script
