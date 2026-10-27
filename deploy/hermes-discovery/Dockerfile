# syntax=docker/dockerfile:1@sha256:ecfaec9ed6d810b56388c508f4121597bfbba70d41a6dfeee4d8cad5f295fc32

# Discovery is a stdlib-only image.  It shares the already approved immutable
# Python/Alpine base with the editorial worker but has no worker/provider code.
FROM python:3.13-alpine@sha256:f3ebba2ace255c93267a0278da88c7f1044432991abc4e6ad20d22e34dd0f8ee

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/hermes \
    HERMES_DISCOVERY_DEFINITIONS=/opt/hermes/config/source-definitions.json

WORKDIR /opt/hermes

COPY discovery_runner.py hermes_health.py hermes-discovery-provenance.json license_bundle.py requirements.lock ./
COPY source-definitions.schema.json /opt/hermes/config/source-definitions.schema.json
COPY LICENSES /opt/licenses-source/

RUN python /opt/hermes/license_bundle.py \
        --output /opt/licenses \
        --manifest /opt/licenses-source/package-license-inventory.json \
        --apk-database /lib/apk/db/installed \
    && python -m pip uninstall --yes pip setuptools wheel \
    && rm -rf /opt/licenses-source /opt/hermes/license_bundle.py /tmp/* /root/.cache \
    && addgroup -S -g 10000 hermes \
    && adduser -S -D -H -u 10000 -G hermes -s /sbin/nologin hermes \
    && mkdir --parents /opt/data /opt/hermes/config \
    && chown hermes:hermes /opt/data \
    && chmod 0700 /opt/data \
    && chmod -R a=rX /opt/licenses /opt/hermes \
    && rm -f /bin/sh /bin/ash /bin/busybox /usr/bin/busybox /sbin/apk /usr/sbin/apk /usr/bin/apk

VOLUME ["/opt/data"]
USER 10000:10000
ENTRYPOINT ["python", "/opt/hermes/discovery_runner.py"]
