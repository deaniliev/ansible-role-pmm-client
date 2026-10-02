import os
import sys

import pytest
from ansible.errors import AnsibleFilterError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "filter_plugins"))

from pmm_client import (  # noqa: E402
    pmm_client_add_argv,
    pmm_client_normalize_service_type,
    pmm_client_remove_argv,
    pmm_client_service_plan,
)


def test_mysql_with_address_and_flags():
    argv = pmm_client_add_argv({
        "type": "mysql",
        "name": "db1-mysql",
        "address": "127.0.0.1:3306",
        "username": "pmm",
        "password": "p@ss w/rd",
        "query_source": "perfschema",
        "custom_labels": {"team": "dba", "tier": "1"},
        "disable_tablestats": True,
        "tls": False,
        "cluster": "",
        "state": "present",
    })
    assert argv == [
        "pmm-admin", "add", "mysql",
        "--custom-labels=team=dba,tier=1",
        "--disable-tablestats",
        "--password=p@ss w/rd",
        "--query-source=perfschema",
        "--username=pmm",
        "db1-mysql", "127.0.0.1:3306",
    ]


def test_postgresql_socket_without_address():
    argv = pmm_client_add_argv({"type": "postgresql", "name": "pg", "socket": "/var/run/postgresql"})
    assert argv == ["pmm-admin", "add", "postgresql", "--socket=/var/run/postgresql", "pg"]


def test_lists_are_comma_joined_and_extra_args_appended():
    argv = pmm_client_add_argv({
        "type": "mongodb", "name": "m", "disable_collectors": ["a", "b"], "extra_args": ["--enable-all-collectors"],
    })
    assert argv == ["pmm-admin", "add", "mongodb", "--disable-collectors=a,b", "--enable-all-collectors", "m"]


def test_external_uses_service_name_flag():
    argv = pmm_client_add_argv({"type": "external", "name": "node-exp", "listen_port": 9100, "group": "custom"})
    assert argv == ["pmm-admin", "add", "external", "--group=custom", "--listen-port=9100", "--service-name=node-exp"]


def test_external_serverless_uses_external_name_and_address_flag():
    argv = pmm_client_add_argv({"type": "external-serverless", "name": "api", "address": "10.0.0.5:9000"})
    assert argv == ["pmm-admin", "add", "external-serverless", "--address=10.0.0.5:9000", "--external-name=api"]


def test_haproxy_rejects_address():
    with pytest.raises(AnsibleFilterError):
        pmm_client_add_argv({"type": "haproxy", "name": "h", "address": "1.2.3.4:8404", "listen_port": 8404})


@pytest.mark.parametrize("svc", [{"type": "oracle", "name": "x"}, {"type": "mysql"}, "mysql"])
def test_invalid_definitions(svc):
    with pytest.raises(AnsibleFilterError):
        pmm_client_add_argv(svc)


@pytest.mark.parametrize("raw,expected", [
    ("SERVICE_TYPE_MYSQL_SERVICE", "mysql"),
    ("SERVICE_TYPE_POSTGRESQL_SERVICE", "postgresql"),
    ("SERVICE_TYPE_EXTERNAL_SERVICE", "external"),
    ("MySQL", "mysql"),
    ("mongodb", "mongodb"),
    ("External:exporter", "external"),
    ("external-serverless", "external"),
])
def test_normalize_service_type(raw, expected):
    assert pmm_client_normalize_service_type(raw) == expected


def test_remove_argv():
    assert pmm_client_remove_argv({"type": "SERVICE_TYPE_MYSQL_SERVICE", "name": "db"}) == [
        "pmm-admin", "remove", "mysql", "db",
    ]


EXISTING = [
    {"service_type": "SERVICE_TYPE_MYSQL_SERVICE", "service_name": "keep"},
    {"service_type": "SERVICE_TYPE_MYSQL_SERVICE", "service_name": "drop"},
    {"service_type": "SERVICE_TYPE_POSTGRESQL_SERVICE", "service_name": "again"},
    {"service_type": "SERVICE_TYPE_MONGODB_SERVICE", "service_name": "stray"},
]
DESIRED = [
    {"type": "mysql", "name": "keep"},
    {"type": "mysql", "name": "drop", "state": "absent"},
    {"type": "postgresql", "name": "again", "recreate": True},
    {"type": "mongodb", "name": "new"},
    {"type": "mysql", "name": "gone-already", "state": "absent"},
]


def test_plan_without_purge():
    plan = pmm_client_service_plan(DESIRED, EXISTING)
    assert plan["remove"] == [{"type": "mysql", "name": "drop"}, {"type": "postgresql", "name": "again"}]
    assert [s["name"] for s in plan["add"]] == ["again", "new"]


def test_plan_with_purge():
    plan = pmm_client_service_plan(DESIRED, EXISTING, purge=True)
    assert plan["remove"][-1] == {"type": "mongodb", "name": "stray"}
    assert len(plan["remove"]) == 3


def test_plan_is_idempotent():
    existing = [{"service_type": "SERVICE_TYPE_MYSQL_SERVICE", "service_name": "keep"}]
    assert pmm_client_service_plan([{"type": "mysql", "name": "keep"}], existing) == {"remove": [], "add": []}


def test_plan_handles_empty_list_output():
    plan = pmm_client_service_plan([{"type": "mysql", "name": "a"}], None)
    assert plan == {"remove": [], "add": [{"type": "mysql", "name": "a"}]}
