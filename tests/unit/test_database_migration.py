# SPDX-License-Identifier: LGPL-3.0-or-later
# tests/unit/test_database_migration.py
"""
Unit tests for database-aware migration.
"""

import logging
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from hyper2kvm.database_migration import (
    DatabaseDetector,
    DatabaseEngine,
    DatabaseInfo,
    DatabaseMigrationOrchestrator,
    GenericDatabaseHandler,
    MongoDBHandler,
    MySQLHandler,
    PostgreSQLHandler,
    RedisHandler,
)


@pytest.fixture
def logger():
    """Create test logger."""
    return logging.getLogger("test")


@pytest.fixture
def mock_vmcraft():
    """Create mock VMCraft instance."""
    g = MagicMock()

    # Mock file system methods
    g.exists = Mock(return_value=True)
    g.is_dir = Mock(return_value=True)
    g.ls = Mock(return_value=["14", "15"])
    g.read_file = Mock(return_value="port = 5432\nmax_connections = 100")

    return g


# DatabaseDetector Tests

def test_detector_detects_postgresql(logger, mock_vmcraft):
    """Test PostgreSQL detection."""
    detector = DatabaseDetector(logger)

    mock_vmcraft.exists = Mock(side_effect=lambda path: "/postgresql" in path)
    mock_vmcraft.ls.return_value = ["14", "15"]

    databases = detector.detect_databases(mock_vmcraft)

    postgresql_dbs = [db for db in databases if db.engine == DatabaseEngine.POSTGRESQL]
    assert len(postgresql_dbs) > 0
    assert postgresql_dbs[0].version in ["14", "15"]


def test_detector_detects_mysql(logger, mock_vmcraft):
    """Test MySQL detection."""
    detector = DatabaseDetector(logger)

    def exists_side_effect(path):
        return "/mysqld" in path or path == "/etc/mysql/my.cnf"

    mock_vmcraft.exists = Mock(side_effect=exists_side_effect)

    databases = detector.detect_databases(mock_vmcraft)

    mysql_dbs = [db for db in databases if db.engine == DatabaseEngine.MYSQL]
    assert len(mysql_dbs) > 0
    assert mysql_dbs[0].port == 3306


def test_detector_detects_mongodb(logger, mock_vmcraft):
    """Test MongoDB detection."""
    detector = DatabaseDetector(logger)

    mock_vmcraft.exists = Mock(side_effect=lambda path: "/mongod" in path)

    databases = detector.detect_databases(mock_vmcraft)

    mongodb_dbs = [db for db in databases if db.engine == DatabaseEngine.MONGODB]
    assert len(mongodb_dbs) > 0
    assert mongodb_dbs[0].port == 27017


def test_detector_detects_redis(logger, mock_vmcraft):
    """Test Redis detection."""
    detector = DatabaseDetector(logger)

    def exists_side_effect(path):
        return "/redis-server" in path or "/redis.conf" in path

    mock_vmcraft.exists = Mock(side_effect=exists_side_effect)

    databases = detector.detect_databases(mock_vmcraft)

    redis_dbs = [db for db in databases if db.engine == DatabaseEngine.REDIS]
    assert len(redis_dbs) > 0
    assert redis_dbs[0].port == 6379


def test_detector_summary(logger):
    """Test database summary generation."""
    detector = DatabaseDetector(logger)

    databases = [
        DatabaseInfo(
            engine=DatabaseEngine.POSTGRESQL,
            version="14",
            instance_name="pg-14",
            port=5432,
            total_size_mb=5000.0
        ),
        DatabaseInfo(
            engine=DatabaseEngine.MYSQL,
            version="8.0",
            instance_name="mysql",
            port=3306,
            total_size_mb=3000.0,
            replication_role="primary"
        )
    ]

    summary = detector.get_database_summary(databases)

    assert summary["total_databases"] == 2
    assert summary["by_engine"]["postgresql"] == 1
    assert summary["by_engine"]["mysql"] == 1
    assert summary["total_size_mb"] == 8000.0
    assert len(summary["requires_special_handling"]) > 0  # MySQL primary flagged


# PostgreSQLHandler Tests

def test_postgresql_pre_migration_check(logger):
    """Test PostgreSQL pre-migration checks."""
    db_info = DatabaseInfo(
        engine=DatabaseEngine.POSTGRESQL,
        version="14",
        data_directory="/tmp/test_pg_data",
        port=5432
    )

    handler = PostgreSQLHandler(logger, db_info)

    with patch("pathlib.Path.exists", return_value=True):
        result = handler.pre_migration_check()

    assert "healthy" in result
    assert "checks" in result
    assert result["checks"]["accessible"] is True


def test_postgresql_quiesce(logger):
    """Test PostgreSQL quiesce operation."""
    db_info = DatabaseInfo(
        engine=DatabaseEngine.POSTGRESQL,
        version="14",
        instance_name="postgres"
    )

    handler = PostgreSQLHandler(logger, db_info)
    result = handler.quiesce_database()

    assert result["success"] is True
    assert "method" in result
    assert result["duration_seconds"] > 0


def test_postgresql_tune_for_kvm(logger):
    """Test PostgreSQL KVM tuning."""
    db_info = DatabaseInfo(
        engine=DatabaseEngine.POSTGRESQL,
        version="14"
    )

    handler = PostgreSQLHandler(logger, db_info)
    result = handler.tune_for_kvm()

    assert len(result["recommended"]) > 0
    assert any("shared_buffers" in rec for rec in result["recommended"])


def test_postgresql_connection_strings(logger):
    """Test PostgreSQL connection string generation."""
    db_info = DatabaseInfo(
        engine=DatabaseEngine.POSTGRESQL,
        version="14",
        port=5432,
        databases=["production"]
    )

    handler = PostgreSQLHandler(logger, db_info)
    conn_strings = handler.get_connection_strings()

    assert "jdbc" in conn_strings
    assert "postgresql://" in conn_strings["native"]
    assert "5432" in conn_strings["psql"]


# MySQLHandler Tests

def test_mysql_pre_migration_check(logger):
    """Test MySQL pre-migration checks."""
    db_info = DatabaseInfo(
        engine=DatabaseEngine.MYSQL,
        version="8.0",
        port=3306
    )

    handler = MySQLHandler(logger, db_info)
    result = handler.pre_migration_check()

    assert result["healthy"] is True
    assert "checks" in result


def test_mysql_quiesce(logger):
    """Test MySQL quiesce operation."""
    db_info = DatabaseInfo(
        engine=DatabaseEngine.MYSQL,
        version="8.0"
    )

    handler = MySQLHandler(logger, db_info)
    result = handler.quiesce_database()

    assert result["success"] is True
    assert result["method"] == "flush_tables_with_read_lock"


def test_mysql_connection_strings(logger):
    """Test MySQL connection string generation."""
    db_info = DatabaseInfo(
        engine=DatabaseEngine.MYSQL,
        version="8.0",
        port=3306,
        databases=["webapp"]
    )

    handler = MySQLHandler(logger, db_info)
    conn_strings = handler.get_connection_strings()

    assert "jdbc" in conn_strings
    assert "mysql://" in conn_strings["native"]
    assert "3306" in conn_strings["cli"]


# MongoDBHandler Tests

def test_mongodb_pre_migration_check(logger):
    """Test MongoDB pre-migration checks."""
    db_info = DatabaseInfo(
        engine=DatabaseEngine.MONGODB,
        version="6.0",
        data_directory="/tmp/test_mongo_data",
        port=27017
    )

    handler = MongoDBHandler(logger, db_info)

    with patch("pathlib.Path.exists", return_value=True):
        result = handler.pre_migration_check()

    assert "healthy" in result
    assert "checks" in result


def test_mongodb_quiesce(logger):
    """Test MongoDB quiesce operation."""
    db_info = DatabaseInfo(
        engine=DatabaseEngine.MONGODB,
        version="6.0"
    )

    handler = MongoDBHandler(logger, db_info)
    result = handler.quiesce_database()

    assert result["success"] is True
    assert result["method"] == "fsyncLock (simulated)"


def test_mongodb_tune_for_kvm(logger):
    """Test MongoDB KVM tuning."""
    db_info = DatabaseInfo(
        engine=DatabaseEngine.MONGODB,
        version="6.0"
    )

    handler = MongoDBHandler(logger, db_info)
    result = handler.tune_for_kvm()

    assert len(result["recommended"]) > 0
    assert any("wiredTiger" in rec for rec in result["recommended"])


def test_mongodb_connection_strings(logger):
    """Test MongoDB connection string generation."""
    db_info = DatabaseInfo(
        engine=DatabaseEngine.MONGODB,
        version="6.0",
        port=27017,
        databases=["myapp"]
    )

    handler = MongoDBHandler(logger, db_info)
    conn_strings = handler.get_connection_strings()

    assert "standard" in conn_strings
    assert "mongodb://" in conn_strings["standard"]


# RedisHandler Tests

def test_redis_pre_migration_check(logger):
    """Test Redis pre-migration checks."""
    db_info = DatabaseInfo(
        engine=DatabaseEngine.REDIS,
        version="7.0",
        data_directory="/tmp/test_redis_data",
        port=6379
    )

    handler = RedisHandler(logger, db_info)

    with patch("pathlib.Path.exists", return_value=True):
        result = handler.pre_migration_check()

    assert "healthy" in result


def test_redis_quiesce(logger):
    """Test Redis quiesce operation."""
    db_info = DatabaseInfo(
        engine=DatabaseEngine.REDIS,
        version="7.0"
    )

    handler = RedisHandler(logger, db_info)
    result = handler.quiesce_database()

    assert result["success"] is True
    assert result["method"] == "bgsave (simulated)"


def test_redis_connection_strings(logger):
    """Test Redis connection string generation."""
    db_info = DatabaseInfo(
        engine=DatabaseEngine.REDIS,
        version="7.0",
        port=6379
    )

    handler = RedisHandler(logger, db_info)
    conn_strings = handler.get_connection_strings()

    assert "redis_uri" in conn_strings
    assert "redis://" in conn_strings["redis_uri"]
    assert "6379" in conn_strings["redis_cli"]


# GenericDatabaseHandler Tests

def test_generic_handler_pre_migration_check(logger):
    """Test generic handler pre-migration checks."""
    db_info = DatabaseInfo(
        engine=DatabaseEngine.ORACLE,
        version="19c",
        data_directory="/tmp/test_oracle_data"
    )

    handler = GenericDatabaseHandler(logger, db_info)

    with patch("pathlib.Path.exists", return_value=True):
        result = handler.pre_migration_check()

    assert "healthy" in result
    assert len(result["warnings"]) > 0  # Should warn about no specialized handler


def test_generic_handler_quiesce(logger):
    """Test generic handler quiesce operation."""
    db_info = DatabaseInfo(
        engine=DatabaseEngine.CASSANDRA,
        version="4.0"
    )

    handler = GenericDatabaseHandler(logger, db_info)
    result = handler.quiesce_database()

    assert result["success"] is True
    assert result["method"] == "offline (VM shutdown)"


def test_generic_handler_tune_for_kvm(logger):
    """Test generic handler KVM tuning."""
    db_info = DatabaseInfo(
        engine=DatabaseEngine.ELASTICSEARCH,
        version="8.0"
    )

    handler = GenericDatabaseHandler(logger, db_info)
    result = handler.tune_for_kvm()

    assert len(result["recommended"]) > 0
    assert any("VirtIO" in rec for rec in result["recommended"])


# DatabaseMigrationOrchestrator Tests

def test_orchestrator_get_handler_postgresql(logger):
    """Test orchestrator returns correct handler for PostgreSQL."""
    orchestrator = DatabaseMigrationOrchestrator(logger)

    db_info = DatabaseInfo(
        engine=DatabaseEngine.POSTGRESQL,
        version="14"
    )

    handler = orchestrator.get_handler(db_info)
    assert isinstance(handler, PostgreSQLHandler)


def test_orchestrator_get_handler_mysql(logger):
    """Test orchestrator returns correct handler for MySQL."""
    orchestrator = DatabaseMigrationOrchestrator(logger)

    db_info = DatabaseInfo(
        engine=DatabaseEngine.MYSQL,
        version="8.0"
    )

    handler = orchestrator.get_handler(db_info)
    assert isinstance(handler, MySQLHandler)


def test_orchestrator_get_handler_mongodb(logger):
    """Test orchestrator returns correct handler for MongoDB."""
    orchestrator = DatabaseMigrationOrchestrator(logger)

    db_info = DatabaseInfo(
        engine=DatabaseEngine.MONGODB,
        version="6.0"
    )

    handler = orchestrator.get_handler(db_info)
    assert isinstance(handler, MongoDBHandler)


def test_orchestrator_get_handler_redis(logger):
    """Test orchestrator returns correct handler for Redis."""
    orchestrator = DatabaseMigrationOrchestrator(logger)

    db_info = DatabaseInfo(
        engine=DatabaseEngine.REDIS,
        version="7.0"
    )

    handler = orchestrator.get_handler(db_info)
    assert isinstance(handler, RedisHandler)


def test_orchestrator_get_handler_generic(logger):
    """Test orchestrator returns generic handler for unsupported database."""
    orchestrator = DatabaseMigrationOrchestrator(logger)

    db_info = DatabaseInfo(
        engine=DatabaseEngine.ORACLE,
        version="19c"
    )

    handler = orchestrator.get_handler(db_info)
    assert isinstance(handler, GenericDatabaseHandler)


def test_orchestrator_pre_migration_checks(logger):
    """Test orchestrator pre-migration checks."""
    orchestrator = DatabaseMigrationOrchestrator(logger)

    databases = [
        DatabaseInfo(
            engine=DatabaseEngine.POSTGRESQL,
            version="14",
            data_directory="/tmp/pg_data"
        ),
        DatabaseInfo(
            engine=DatabaseEngine.MYSQL,
            version="8.0"
        )
    ]

    with patch("pathlib.Path.exists", return_value=True):
        result = orchestrator.pre_migration_checks(databases)

    assert "all_healthy" in result
    assert len(result["checks"]) == 2


def test_orchestrator_quiesce_databases(logger):
    """Test orchestrator database quiesce."""
    orchestrator = DatabaseMigrationOrchestrator(logger)

    databases = [
        DatabaseInfo(
            engine=DatabaseEngine.POSTGRESQL,
            version="14"
        )
    ]

    result = orchestrator.quiesce_databases(databases)

    assert result["success"] is True
    assert len(result["databases"]) == 1
    assert result["total_duration_seconds"] > 0


def test_orchestrator_resume_databases(logger):
    """Test orchestrator database resume."""
    orchestrator = DatabaseMigrationOrchestrator(logger)

    databases = [
        DatabaseInfo(
            engine=DatabaseEngine.MYSQL,
            version="8.0"
        )
    ]

    result = orchestrator.resume_databases(databases)

    assert result["success"] is True
    assert len(result["databases"]) == 1


def test_orchestrator_validate_post_migration(logger):
    """Test orchestrator post-migration validation."""
    orchestrator = DatabaseMigrationOrchestrator(logger)

    databases = [
        DatabaseInfo(
            engine=DatabaseEngine.POSTGRESQL,
            version="14"
        )
    ]

    result = orchestrator.validate_post_migration(databases, migrated_vm_ip="192.168.1.100")

    assert "all_valid" in result
    assert len(result["validations"]) == 1


def test_orchestrator_tune_for_kvm(logger):
    """Test orchestrator KVM tuning."""
    orchestrator = DatabaseMigrationOrchestrator(logger)

    databases = [
        DatabaseInfo(
            engine=DatabaseEngine.POSTGRESQL,
            version="14"
        ),
        DatabaseInfo(
            engine=DatabaseEngine.MONGODB,
            version="6.0"
        )
    ]

    result = orchestrator.tune_for_kvm(databases)

    assert len(result["databases"]) == 2
    assert len(result["all_recommended"]) > 0


def test_orchestrator_generate_migration_guide(logger):
    """Test migration guide generation."""
    orchestrator = DatabaseMigrationOrchestrator(logger)

    databases = [
        DatabaseInfo(
            engine=DatabaseEngine.POSTGRESQL,
            version="14",
            instance_name="pg-prod",
            data_directory="/var/lib/postgresql/14/main",
            config_file="/etc/postgresql/14/main/postgresql.conf"
        )
    ]

    guide = orchestrator.generate_migration_guide(
        databases,
        new_hostname="prod-db-kvm",
        new_ip="192.168.100.50"
    )

    assert "Database Migration Post-Migration Guide" in guide
    assert "POSTGRESQL" in guide
    assert "pg-prod" in guide
    assert "prod-db-kvm" in guide
    assert "192.168.100.50" in guide
    assert "Connection Strings" in guide
    assert "Performance Tuning Recommendations" in guide


def test_orchestrator_full_workflow(logger, mock_vmcraft):
    """Test complete orchestration workflow."""
    orchestrator = DatabaseMigrationOrchestrator(logger)

    # Setup mock to detect PostgreSQL
    mock_vmcraft.exists = Mock(side_effect=lambda path: "/postgresql" in path)
    mock_vmcraft.ls.return_value = ["14"]

    with patch("pathlib.Path.exists", return_value=True):
        with patch("pathlib.Path.write_text"):
            result = orchestrator.orchestrate_migration(
                mock_vmcraft,
                new_hostname="test-kvm",
                new_ip="192.168.1.100",
                output_dir=Path("/tmp")
            )

    assert result["success"] is True
    assert result["databases_detected"] > 0
    assert result["health_checks_passed"] is True
    assert result["quiesce_successful"] is True
    assert result["resume_successful"] is True


def test_orchestrator_no_databases_workflow(logger, mock_vmcraft):
    """Test orchestration workflow with no databases."""
    orchestrator = DatabaseMigrationOrchestrator(logger)

    # Setup mock to not detect any databases
    mock_vmcraft.exists = Mock(return_value=False)

    result = orchestrator.orchestrate_migration(mock_vmcraft)

    assert result["success"] is True
    assert result["databases_detected"] == 0


def test_orchestrator_health_check_failure(logger, mock_vmcraft):
    """Test orchestration aborts on health check failure."""
    orchestrator = DatabaseMigrationOrchestrator(logger)

    # Setup mock to detect PostgreSQL but fail health check
    mock_vmcraft.exists = Mock(side_effect=lambda path: "/postgresql" in path)
    mock_vmcraft.ls.return_value = ["14"]

    with patch("pathlib.Path.exists", return_value=False):  # Fail data directory check
        result = orchestrator.orchestrate_migration(mock_vmcraft)

    assert result["success"] is False
    assert result["health_checks_passed"] is False
    assert len(result["errors"]) > 0
