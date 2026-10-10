# YFC report fonts

Local static TrueType instances of the existing YFC web fonts: Inter 4.001 and Oswald 4.103. Inter is used for body text, labels, tables and values (400/700); Oswald Bold is used for report titles and section headings (700).

The Latin and Cyrillic WOFF2 subsets from `frontend/public/assets/fonts/` were instantiated at the specified weight and merged with fontTools 4.66.1 / Brotli 1.2.0. These are build tools only; PDF generation needs no fontTools, network or system fonts. Full Russian Cyrillic, Latin, digits and report punctuation are checked before packaging. Embedding permission (`OS/2.fsType=0`) is verified. The original OFL-1.1 licenses are distributed alongside these files; they permit use, modification, redistribution and document embedding under their terms. No reserved font name is declared in these license files.

## Packaged files

- `Inter-Regular.ttf`: weight 400, SHA-256 `5f92dc98b56f93bb7114fc54981b709865b30a76970d2e3076d0cbb50eeee005`.
- `Inter-Bold.ttf`: weight 700, SHA-256 `10145a5120b1baafab8cc9467828125846d9177f2226f1fe9962e94af18b9a19`.
- `Oswald-Bold.ttf`: weight 700, SHA-256 `7261d07c7b7bc41732cfd15d808e5c6ae1a4e331bac22246383e6741b33dc44d`.

## Original web assets

- `inter-cyrillic.woff2`: `71d5ee93cc1e9f1d520a3a8b66456de18c7879d8df09d57fcd2eaff75fef0075`.
- `inter-latin.woff2`: `3100e775e8616cd2611beecfa23a4263d7037586789b43f035236a2e6fbd4c62`.
- `oswald-cyrillic.woff2`: `95c3d8d1db01b5ecd85b0d90aa81d39d24231f74de28c7418cfd8c08261fe929`.
- `oswald-latin.woff2`: `571f3457dab507b6f2ce5394d593ca015251b69fea81ab7a546bd2368e9fc3ed`.
