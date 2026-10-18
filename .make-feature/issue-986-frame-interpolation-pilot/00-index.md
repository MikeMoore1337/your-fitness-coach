# Make Feature: Issue #1110 — AI frame interpolation pilot

- Stage: implementation complete; technical evidence complete; owner visual acceptance pending.
- Depth: deep — это новый GPU/runtime-пилот с provenance, реальными PTS, resume и QC, но без
  изменения production media/catalog.
- Base: `origin/master` at `57e4393e2352e18a2e43e55b3698cb31c53f6a5f`.
- Branch: `codex/issue-986-frame-interpolation-pilot-local`.
- Remote PR branch: `codex/issue-986-frame-interpolation-pilot`.
- Worktree: `.artifacts/worktrees/986-frame-interpolation-pilot`.
- Issue: [#1110](https://github.com/MikeMoore1337/your-fitness-coach/issues/1110); Draft PR:
  [#1111](https://github.com/MikeMoore1337/your-fitness-coach/pull/1111).
- Scope: восемь AI-upscaled кандидатов из контекста #986, RIFE `8/12/16 FPS`, локальная
  галерея, contact sheets, отчёт и тесты.
- Explicit exclusions: production manifest/media, PR #1094/#1109 branches, model/binary files,
  merge/deploy, автоматическая визуальная приёмка техники.

## Decisions

- D1: использовать официальный portable `rife-ncnn-vulkan` `20221029` с моделью `rife-v4`;
  `-s` поддерживает произвольный timestep, а Windows decimal separator передаётся через comma.
- D2: строить план по реальным source PTS и не замыкать последнюю пару на первый кадр GIF.
- D3: кодировать только CFR MP4 с явным количеством кадров; для длительности, не кратной FPS,
  документировать неизбежную quantization delta вместо скрытого VFR rounding.
- D4: любой частичный, несовпадающий или изменённый артефакт вызывает fail-closed; resume
  разрешён только при совпадении signature и SHA-256.

## Acceptance gates

- C1: source provenance, source GIF/MP4 SHA-256, real PTS and source worktree integrity — passed.
- C2: 24/24 GPU variants, H.264/yuv420p/720×720/no audio, complete decode, monotonic PTS — passed.
- C3: local gallery and 16 contact sheets — passed; synthetic/local evidence only.
- C4: targeted pytest and Ruff — passed; exact-head PR CI is queued/pending on GitHub.
- C5: owner visual acceptance of motion/technique, merge, release and production smoke — pending.
