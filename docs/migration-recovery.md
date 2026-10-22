# MySQL migration recovery

Alembic is the only supported schema initializer. Application startup never creates tables or
runs migrations. Run every command below against the intended database explicitly; never point
these commands at an unknown URL.

## Before changing a populated database

1. Stop application writers or put the service in maintenance mode.
2. Take a restorable backup and keep it outside the database host. For example, let `mysqldump`
   prompt for the password instead of putting it in shell history:

   ```powershell
   mysqldump -h <host> -P <port> -u <user> -p --single-transaction --routines --events --databases <database> > lexrag-before-migration.sql
   ```

3. Set the exact connection URL and inspect both the database state and available chain:

   ```powershell
   $env:DATABASE_URL = "mysql+pymysql://<user>:<password>@<host>:<port>/<database>?charset=utf8mb4"
   python -m alembic current
   python -m alembic heads
   python -m alembic history --verbose
   ```

## Repair and re-run

For a normal interrupted or pending upgrade, preserve the backup, correct the underlying
connection/permissions issue, then re-run the forward migration:

```powershell
python -m alembic upgrade head
python -m alembic current
```

`current` must report the same revision shown by `heads`. If `alembic_version` disagrees with the
actual schema, stop and investigate the specific failed revision before changing version state.
`alembic stamp <revision>` is a manual incident-recovery action only after an operator has verified
that schema and data already match that revision; it does not run migration SQL and is not a fix for
a partial migration.

Do not use automatic destructive downgrade or schema recreation as recovery. Any downgrade,
table drop, or restore must be an explicit, reviewed incident action performed from the verified
backup.

## Isolated contract check

The real MySQL test is deliberately opt-in and never uses a developer database. It starts a
randomly named `mysql:8.4` Docker container, creates random schemas only inside that container,
and removes each schema and the exact container during teardown:

```powershell
$env:RUN_MYSQL_MIGRATION_INTEGRATION = "1"
python -m pytest tests/test_alembic_mysql_integration.py -q
```
