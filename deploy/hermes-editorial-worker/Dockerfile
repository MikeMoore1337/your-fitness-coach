# syntax=docker/dockerfile:1@sha256:ecfaec9ed6d810b56388c508f4121597bfbba70d41a6dfeee4d8cad5f295fc32

# The digest is the amd64 Python 3.13 Alpine base approved for the bounded worker.
FROM python:3.13-alpine@sha256:f3ebba2ace255c93267a0278da88c7f1044432991abc4e6ad20d22e34dd0f8ee

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/opt/hermes \
    HERMES_HOME=/opt/data \
    HERMES_ENABLE_PROJECT_PLUGINS=0 \
    HERMES_RUNTIME_UPSTREAM_TAG=v2026.8.31 \
    HERMES_RUNTIME_UPSTREAM_COMMIT=29112bef099274229cadff79cdff7bf7b99c4b77

WORKDIR /opt/hermes

COPY requirements.lock /tmp/requirements.lock
RUN python -m pip install --no-cache-dir --only-binary=:all: --require-hashes --requirement /tmp/requirements.lock

COPY editorial_worker.py config.schema.json hermes-provenance.json license_bundle.py ./
COPY LICENSES /opt/licenses-source/

# Generate license/NOTICE evidence while the exact locked distributions and APK database exist.
RUN python /opt/hermes/license_bundle.py \
        --output /opt/licenses \
        --lock /tmp/requirements.lock \
        --source-manifest /opt/licenses-source/package-license-inventory.json \
        --upstream-license /opt/licenses-source/HERMES-LICENSE \
        --apk-database /lib/apk/db/installed \
    && python -m pip uninstall --yes pip setuptools wheel \
    && rm -rf /opt/licenses-source /opt/hermes/license_bundle.py /tmp/requirements.lock /root/.cache \
    && addgroup -S -g 10000 hermes \
    && adduser -S -D -H -u 10000 -G hermes -s /sbin/nologin hermes \
    && mkdir --parents /opt/data \
    && chown hermes:hermes /opt/data \
    && chmod 0700 /opt/data \
    && chmod -R a=rX /opt/licenses \
    && rm -f /bin/sh /bin/ash /bin/busybox /usr/bin/busybox /sbin/apk /usr/sbin/apk /usr/bin/apk

VOLUME ["/opt/data"]
USER 10000:10000
ENTRYPOINT ["python", "/opt/hermes/editorial_worker.py"]
