# ansible-role-pmm-client

Ansible role that installs [Percona Monitoring and Management (PMM) 3 Client](https://docs.percona.com/percona-monitoring-and-management/3/install-pmm/install-pmm-client/index.html),
registers the node with PMM Server and manages the monitored services
(MySQL, PostgreSQL, MongoDB, Valkey/Redis, ProxySQL, HAProxy and external exporters).

The steps follow the official documentation:

1. install `percona-release` and run `percona-release enable pmm3-client`;
2. install the `pmm-client` package and make sure `pmm-agent` is running;
3. register the node with `pmm-admin config --server-url=https://service_token:<glsa_token>@<server>:443`;
4. add services with `pmm-admin add <type> ...` and remove them with `pmm-admin remove <type> <name>`.

## Requirements

From the [PMM Client prerequisites](https://docs.percona.com/percona-monitoring-and-management/3/install-pmm/install-pmm-client/prerequisites.html):

- 64-bit Linux: Debian, Ubuntu, RHEL and compatible (Rocky, Alma, Oracle Linux), Amazon Linux 2023;
- x86_64 or ARM64;
- ~100 MB of disk for the installation plus up to 1 GB used by vmagent to cache metrics during network outages;
- 100–200 MB of RAM per monitored database;
- outgoing access to PMM Server on port 443 (or the port it is published on), and to the monitored databases;
- a PMM **service account token** (`glsa_...`), recommended by Percona, or an admin username/password;
- a database user for PMM on each monitored database (see the per-database setup pages in the PMM documentation,
  e.g. [MySQL](https://docs.percona.com/percona-monitoring-and-management/3/install-pmm/install-pmm-client/connect-database/mysql/mysql.html)).

The role needs `become: true` and gathered facts. Ansible 2.15+.

Tested with PMM Client 3.9.1 on Debian 12, Ubuntu 24.04 and Rocky Linux 9.

## Role variables

See [defaults/main.yml](defaults/main.yml) and [meta/argument_specs.yml](meta/argument_specs.yml) for the full list.

### Installation

| Variable | Default | Description |
|---|---|---|
| `pmm_client_enabled` | `true` | Run the role on this host. `false` skips the host entirely (see below) |
| `pmm_client_manage_repo` | `true` | Install `percona-release` and enable the repository |
| `pmm_client_repo_name` | `pmm3-client` | Repository passed to `percona-release enable` |
| `pmm_client_repo_component` | `release` | `release`, `testing` or `experimental` |
| `pmm_client_version` | `""` | Pin a version, e.g. `3.9.1`. Empty installs the latest |
| `pmm_client_package_state` | `present` | `present` or `latest` (when no version is pinned) |

`pmm_client_enabled` and `pmm_client_register` do different things:

| | Package and `pmm-agent` | Registration | Services |
|---|---|---|---|
| `pmm_client_enabled: false` | not installed | no | no |
| `pmm_client_register: false` | installed and running | no | no |
| both `true` (default) | installed and running | yes | managed |

`pmm_client_enabled: false` does not uninstall an existing client; it only
makes the role leave the host alone. Example in `host_vars/db-test01.yml`:

```yaml
pmm_client_enabled: false
```

### Registration

| Variable | Default | Description |
|---|---|---|
| `pmm_client_register` | `true` | Register the node and manage services |
| `pmm_client_server_host` | `""` | PMM Server host (required) |
| `pmm_client_server_port` | `443` | PMM Server port |
| `pmm_client_server_token` | `""` | Service account token (`glsa_...`) |
| `pmm_client_server_username` / `_password` | `admin` / `""` | Used when no token is set |
| `pmm_client_server_insecure_tls` | `false` | Accept a self-signed server certificate |
| `pmm_client_node_address` | default IPv4 | Node address |
| `pmm_client_node_type` | `generic` | `generic` or `container` |
| `pmm_client_node_name` | `inventory_hostname` | Node name in PMM |
| `pmm_client_node_model`, `_region`, `_az` | `""` | Optional node attributes |
| `pmm_client_node_custom_labels` | `{}` | Custom labels for the node |
| `pmm_client_metrics_mode` | `auto` | `auto`, `push` or `pull` |
| `pmm_client_disable_collectors` | `[]` | node_exporter collectors to disable |
| `pmm_client_config_extra_args` | `[]` | Extra raw arguments for `pmm-admin config` |
| `pmm_client_config_force` | `false` | Pass `--force` (replace an existing node with the same name) |
| `pmm_client_force_register` | `false` | Run `pmm-admin config` even if already registered |

`pmm-admin config` runs only when `pmm-agent` is not registered yet (no `id` in
`/usr/local/percona/pmm/config/pmm-agent.yaml`) or is registered with a different
server address, so the role is idempotent.

### Services

| Variable | Default | Description |
|---|---|---|
| `pmm_client_services` | `[]` | Services to monitor (see below) |
| `pmm_client_services_purge` | `false` | Remove services on this node that are not listed |
| `pmm_client_no_log` | `true` | Hide `pmm-admin` command lines, which contain passwords |

Each entry of `pmm_client_services` has these reserved keys:

| Key | Required | Description |
|---|---|---|
| `type` | yes | `mysql`, `postgresql`, `mongodb`, `valkey`, `proxysql`, `haproxy`, `external`, `external-serverless` |
| `name` | yes | Service name; used to detect whether the service already exists |
| `address` | no | `host:port` (mysql, postgresql, mongodb, valkey, proxysql, external-serverless) |
| `state` | no | `present` (default) or `absent` |
| `recreate` | no | Remove and add the service on every run, to apply changed options |
| `extra_args` | no | List of raw arguments appended to `pmm-admin add` |

**Every other key becomes a `pmm-admin add` flag**, so all options of your pmm-admin
version are available without changes to the role:

- underscores become dashes: `query_source: perfschema` → `--query-source=perfschema`;
- `true` becomes a bare flag: `disable_tablestats: true` → `--disable-tablestats`;
- `false`, `null` and empty values are skipped;
- dicts become `k=v,k=v`: `custom_labels: {team: dba}` → `--custom-labels=team=dba`;
- lists become `a,b`: `disable_collectors: [a, b]` → `--disable-collectors=a,b`.

Run `pmm-admin add <type> --help` on a client for the list of flags.

#### `query_source`

Selects where Query Analytics (QAN) takes query data from. The accepted values depend on the service type:

| Type | Value | Source | Database requirements |
|---|---|---|---|
| `mysql` | `slowlog` (default) | Slow query log | `slow_query_log=ON`, `long_query_time=0` recommended |
| | `perfschema` | Performance Schema | `performance_schema=ON` with statement consumers enabled |
| | `none` | QAN disabled, metrics only | — |
| `postgresql` | `pgstatmonitor` (default) | `pg_stat_monitor` extension (Percona); adds query examples, histograms and time buckets | `shared_preload_libraries = 'pg_stat_monitor'` and `CREATE EXTENSION pg_stat_monitor;` |
| | `pgstatements` | `pg_stat_statements` extension | `shared_preload_libraries = 'pg_stat_statements'` and `CREATE EXTENSION pg_stat_statements;` |
| | `none` | QAN disabled, metrics only | — |
| `mongodb` | `profiler` (default) | Database profiler | Profiling enabled (`operationProfiling.mode: all` or `slowOp`) |
| | `mongolog` | mongod log file | Slow operations written to the log; pmm-agent can read the log file |
| | `none` | QAN disabled, metrics only | — |

pmm-admin rejects invalid values for MySQL and MongoDB, but **not for PostgreSQL**:
a typo such as `pg_stat_monitor` adds the service without QAN and without an error.

#### `custom_labels`

Supported by all service types (and by the node itself through
`pmm_client_node_custom_labels`). Give it as a dict or as a ready string:

```yaml
custom_labels: {role: db, team: dba}   # --custom-labels=role=db,team=dba
custom_labels: "role=db,team=dba"      # same result
```

Label names must match `[a-zA-Z_][a-zA-Z0-9_]*` and must not start with `__`.
Avoid names of the labels PMM sets itself (`service_type`, `service_name`,
`node_name`, `node_type`, `environment`, `cluster`, `replication_set`, ...):
use the dedicated options (`environment`, `cluster`, `replication_set`) for those.
Like other options, labels of an existing service change only with `recreate: true`.

Services are compared **by name** with `pmm-admin list --json`. An existing service
is not modified when its options change; set `recreate: true` for one run (or remove
it with `state: absent` and add it again) to apply new options.

## Check mode

The role supports `--check` (and `--diff`):

- on a host where pmm-client is already installed, `pmm-admin list --json` is run
  (read-only) and the services that would be added or removed, and a pending
  registration, are reported as `changed`;
- on a new host, the repository and package steps are reported, while starting
  `pmm-agent`, registration and services are skipped with a message, because
  neither `pmm-agent` nor `pmm-admin` exist before a real run.

On Debian/Ubuntu the `apt` module needs `python3-apt` on the target to run in
check mode (it installs it automatically only on a real run).

## Example playbook

```yaml
- hosts: databases
  become: true
  roles:
    - role: ansible-role-pmm-client
      vars:
        pmm_client_server_host: pmm.example.com
        pmm_client_server_token: "{{ vault_pmm_service_token }}"
        pmm_client_server_insecure_tls: true
        pmm_client_node_custom_labels:
          dc: sofia
        pmm_client_services:
          - type: mysql
            name: "{{ inventory_hostname }}-mysql"
            address: 127.0.0.1:3306
            username: pmm
            password: "{{ vault_pmm_mysql_password }}"
            query_source: perfschema
            environment: production
            cluster: main-cluster
            replication_set: rs1

          - type: mysql
            name: "{{ inventory_hostname }}-mysql-socket"
            socket: /var/run/mysqld/mysqld.sock
            username: pmm
            password: "{{ vault_pmm_mysql_password }}"
            query_source: slowlog
            size_slow_logs: 1GiB

          - type: postgresql
            name: "{{ inventory_hostname }}-postgresql"
            address: 127.0.0.1:5432
            username: pmm
            password: "{{ vault_pmm_pg_password }}"
            query_source: pgstatmonitor
            custom_labels:
              label_1: db
              label_2: dba

          - type: mongodb
            name: "{{ inventory_hostname }}-mongodb"
            address: 127.0.0.1:27017
            username: pmm
            password: "{{ vault_pmm_mongo_password }}"
            query_source: profiler
            enable_all_collectors: true

          - type: valkey
            name: "{{ inventory_hostname }}-valkey"
            address: 127.0.0.1:6379
            password: "{{ vault_pmm_valkey_password }}"

          - type: proxysql
            name: "{{ inventory_hostname }}-proxysql"
            address: 127.0.0.1:6032
            username: radmin
            password: "{{ vault_proxysql_admin_password }}"

          - type: haproxy
            name: "{{ inventory_hostname }}-haproxy"
            listen_port: 8404

          - type: external
            name: "{{ inventory_hostname }}-node-custom"
            listen_port: 9256
            group: process

          - type: mysql
            name: old-mysql
            state: absent
```

## Testing

```bash
pytest tests/unit
```

```bash
ansible-lint
```

## License

MIT
