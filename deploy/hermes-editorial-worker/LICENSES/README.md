# Task 129: license/NOTICE bundle

Этот каталог является частью build context hardened worker. Docker build запускает
`license_bundle.py` после установки exact lock и формирует `/opt/licenses` в image.

В bundle входят:

- `HERMES-LICENSE` — MIT license exact Hermes provenance;
- `NOTICE` — deterministic index of the included obligations;
- `python/` — license/copyright/NOTICE files установленных Python distributions;
- `alpine-installed-packages.txt` — exact APK database snapshot pinned base image;
- `package-license-inventory.json` — deterministic Python/APK inventory и SPDX identifiers;
  APK license fields сохраняются verbatim.

Bundle нельзя редактировать вручную после изменения lock или base digest: нужно заново
выполнить build. В image нет credentials, source packets, Telegram tokens или YFC secrets.
