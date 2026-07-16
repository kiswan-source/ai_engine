#!/bin/sh
# Fase 1 (pg_hba.conf trust-loopback hardening, follow-up to SEC-2).
#
# The official postgres/postgis image's docker-entrypoint.sh auto-generates
# pg_hba.conf at initdb time with `trust` for 127.0.0.1/::1 (and the local
# Unix socket) whenever POSTGRES_HOST_AUTH_METHOD is unset — meaning ANY
# process able to reach the database's TCP loopback address (i.e. anything
# else running on the same host, not just this container) could connect
# with any password, or none, regardless of how strong the real password
# is. This was found and fixed live on the already-initialized volume
# (`ALTER ROLE`/pg_hba.conf edit + reload, no restart); this script is the
# reproducible half — it runs automatically in /docker-entrypoint-initdb.d/
# on any FRESH volume (empty $PGDATA), after initdb has already created the
# default pg_hba.conf but before the server starts for real, so a new
# deployment doesn't regenerate the same gap.
#
# The Unix-socket `local` rule is deliberately left as `trust` — it requires
# actual filesystem access to the socket inside this container (a narrower,
# different threat model than "reachable via the host's loopback network
# interface"), and operators rely on it for `docker exec ... psql` access.
set -eu

HBA="$PGDATA/pg_hba.conf"

sed -i \
  -e 's/^\(host[[:space:]]\+all[[:space:]]\+all[[:space:]]\+127\.0\.0\.1\/32[[:space:]]\+\)trust$/\1scram-sha-256/' \
  -e 's/^\(host[[:space:]]\+all[[:space:]]\+all[[:space:]]\+::1\/128[[:space:]]\+\)trust$/\1scram-sha-256/' \
  -e 's/^\(host[[:space:]]\+replication[[:space:]]\+all[[:space:]]\+127\.0\.0\.1\/32[[:space:]]\+\)trust$/\1scram-sha-256/' \
  -e 's/^\(host[[:space:]]\+replication[[:space:]]\+all[[:space:]]\+::1\/128[[:space:]]\+\)trust$/\1scram-sha-256/' \
  "$HBA"

echo "harden_pg_hba.sh: pg_hba.conf loopback rules require scram-sha-256 (Unix socket 'local' rule left as-is)."
