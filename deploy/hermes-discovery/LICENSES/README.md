# Task 129 discovery license/NOTICE bundle

Этот каталог является частью build context stdlib-only discovery runner. Docker build
запускает `license_bundle.py` и создаёт `/opt/licenses` из PSF-2.0 Python license и
точного APK inventory pinned base image.

Discovery runner не устанавливает third-party Python packages и не содержит Hermes
monolith, provider credentials, YFC secrets, Telegram adapters или source packets.
