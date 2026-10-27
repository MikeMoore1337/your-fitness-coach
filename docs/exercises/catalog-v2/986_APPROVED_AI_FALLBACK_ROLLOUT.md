# #986 - Four owner-approved AI animation fallbacks

Visual acceptance 2026-10-17 of pilot [#1073](https://github.com/MikeMoore1337/your-fitness-coach/pull/1073). Runtime prerequisite: [#1070](https://github.com/MikeMoore1337/your-fitness-coach/pull/1070).

## Scope

Four animations without semantically verified native HD video: machine-chest-press (147,140 bytes), deadlift (111,130), russian-twist (196,448), walking-lunge (160,255). These 614,973 bytes are four unchanged RealESRGAN_x4plus MP4 720x720 binaries reviewed in PR #1073. They are not genuine source HD.

Native verified videos remain at 77 of 206. The four AI-upscaled animations have separate provenance and count. Each original GymVisual 180x180 animated GIF stays byte-identical, remains the canonical manifest source, and is used if video playback fails. Reduced motion and catalog thumbnails display static posters. No other animation is replaced.

The manifest records source asset ID, original source checksum, source timing and frame count, AI model, rights basis, non-native-HD flag, approved pilot, derivative byte size and checksum. Validator rejects unknown AI exercises and checks every committed media binary.

No external services or model inference are required at runtime. Browser validation must cover mobile Safari and Telegram Mini App before post-release acceptance. Issue #986 stays open for the remaining GIF-only / blocked exercises and final acceptance.
