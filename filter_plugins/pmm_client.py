"""Filters that build pmm-admin command lines for the pmm_client role."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import re

from ansible.errors import AnsibleFilterError
from ansible.module_utils.six import string_types

SERVICE_TYPES = (
    "mysql",
    "postgresql",
    "mongodb",
    "valkey",
    "proxysql",
    "haproxy",
    "external",
    "external-serverless",
)

# Keys of a service definition that are not converted into --flags.
RESERVED_KEYS = ("type", "name", "address", "state", "recreate", "extra_args")

# How the service name is passed for each type. Types missing here take the
# name as the first positional argument.
NAME_FLAGS = {
    "external": "--service-name",
    "external-serverless": "--external-name",
}

# Types whose address is given as the second positional argument.
POSITIONAL_ADDRESS_TYPES = ("mysql", "postgresql", "mongodb", "valkey", "proxysql")


def _flag_value(value):
    if isinstance(value, dict):
        return ",".join("%s=%s" % (k, v) for k, v in value.items())
    if isinstance(value, (list, tuple)):
        return ",".join(str(v) for v in value)
    return str(value)


def _validate(service):
    if not isinstance(service, dict):
        raise AnsibleFilterError("pmm_client: service definition must be a dict, got %r" % (service,))
    service_type = service.get("type")
    if service_type not in SERVICE_TYPES:
        raise AnsibleFilterError(
            "pmm_client: unsupported service type %r, expected one of: %s"
            % (service_type, ", ".join(SERVICE_TYPES))
        )
    if not service.get("name"):
        raise AnsibleFilterError("pmm_client: service of type %s has no name" % service_type)
    return service_type


def pmm_client_add_argv(service, binary="pmm-admin"):
    """Return the argv list for `pmm-admin add` from a service definition.

    Every key that is not reserved becomes a flag: underscores turn into
    dashes, ``true`` renders as a bare ``--flag``, ``false``/empty values are
    skipped, dicts render as ``k=v,k=v`` and lists as ``a,b``.
    """
    service_type = _validate(service)
    address = service.get("address")

    argv = [binary, "add", service_type]

    for key in sorted(service):
        if key in RESERVED_KEYS:
            continue
        value = service[key]
        if value is None or value is False or value == "" or value == {} or value == []:
            continue
        flag = "--" + key.replace("_", "-")
        if value is True:
            argv.append(flag)
        else:
            argv.append("%s=%s" % (flag, _flag_value(value)))

    if address and service_type not in POSITIONAL_ADDRESS_TYPES:
        if service_type == "external-serverless":
            argv.append("--address=%s" % address)
        else:
            raise AnsibleFilterError(
                "pmm_client: 'address' is not supported for %s services, use host/listen_port instead"
                % service_type
            )

    extra_args = service.get("extra_args") or []
    if isinstance(extra_args, string_types):
        raise AnsibleFilterError("pmm_client: extra_args must be a list")
    argv.extend(str(a) for a in extra_args)

    if service_type in NAME_FLAGS:
        argv.append("%s=%s" % (NAME_FLAGS[service_type], service["name"]))
    else:
        argv.append(service["name"])
        if address and service_type in POSITIONAL_ADDRESS_TYPES:
            argv.append(str(address))

    return argv


def pmm_client_normalize_service_type(value):
    """Map a service_type from `pmm-admin list --json` to a `pmm-admin remove` type.

    Handles both API enum names (SERVICE_TYPE_MYSQL_SERVICE) and short or
    human-readable names (mysql, MySQL, External).
    """
    normalized = str(value).lower()
    normalized = re.sub(r"^service_type_", "", normalized)
    normalized = re.sub(r"_?service$", "", normalized)
    normalized = normalized.replace("_", "-")
    if normalized.startswith("external"):
        return "external"
    return normalized


def pmm_client_remove_argv(service, binary="pmm-admin"):
    """Return the argv list for `pmm-admin remove` from a service definition."""
    service_type = pmm_client_normalize_service_type(service.get("type", ""))
    name = service.get("name")
    if not name:
        raise AnsibleFilterError("pmm_client: cannot remove a service without a name")
    return [binary, "remove", service_type, name]


def pmm_client_service_plan(desired, existing, purge=False):
    """Compute which services to remove and add.

    ``desired`` is pmm_client_services, ``existing`` is the ``service`` list
    of `pmm-admin list --json`. Returns ``{"remove": [...], "add": [...]}``
    where removals are ``{"type", "name"}`` dicts using the type reported by
    the server, and additions are service definitions from ``desired``.
    """
    existing_by_name = {}
    for svc in existing or []:
        existing_by_name[svc.get("service_name")] = pmm_client_normalize_service_type(svc.get("service_type", ""))

    remove, add = [], []
    desired_names = set()
    for svc in desired or []:
        name = svc.get("name")
        desired_names.add(name)
        state = svc.get("state") or "present"
        if state not in ("present", "absent"):
            raise AnsibleFilterError("pmm_client: invalid state %r for service %s" % (state, name))
        exists = name in existing_by_name
        if exists and (state == "absent" or svc.get("recreate")):
            remove.append({"type": existing_by_name[name], "name": name})
        if state == "present" and (not exists or svc.get("recreate")):
            _validate(svc)
            add.append(svc)

    if purge:
        for name in sorted(n for n in existing_by_name if n not in desired_names):
            remove.append({"type": existing_by_name[name], "name": name})

    return {"remove": remove, "add": add}


class FilterModule(object):
    def filters(self):
        return {
            "pmm_client_add_argv": pmm_client_add_argv,
            "pmm_client_remove_argv": pmm_client_remove_argv,
            "pmm_client_normalize_service_type": pmm_client_normalize_service_type,
            "pmm_client_service_plan": pmm_client_service_plan,
        }
