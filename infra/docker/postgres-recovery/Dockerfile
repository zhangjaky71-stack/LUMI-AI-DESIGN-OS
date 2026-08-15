ARG POSTGRES_IMAGE=pgvector/pgvector:0.8.6-pg17-bookworm
FROM ${POSTGRES_IMAGE}

USER root
COPY primary-entrypoint.sh /usr/local/bin/lumi-postgres-primary-entrypoint
COPY backup.sh /usr/local/bin/lumi-postgres-backup
COPY restore-entrypoint.sh /usr/local/bin/lumi-postgres-restore-entrypoint
COPY recovery-pg_hba.conf /etc/postgresql/recovery-pg_hba.conf
RUN chmod 0755 \
      /usr/local/bin/lumi-postgres-primary-entrypoint \
      /usr/local/bin/lumi-postgres-backup \
      /usr/local/bin/lumi-postgres-restore-entrypoint \
    && chmod 0644 /etc/postgresql/recovery-pg_hba.conf

ENTRYPOINT ["lumi-postgres-primary-entrypoint"]
CMD ["postgres"]
