# CHANGELOG

<!-- version list -->

## v2.3.0 (2026-06-10)

### Features

- **ui**: Add runner command to main keyboard and start menu
  ([#8](https://github.com/AhmedTyson/TeamsLeech-Bot/pull/8),
  [`5f700f3`](https://github.com/AhmedTyson/TeamsLeech-Bot/commit/5f700f3d65a6aaf578727752a56c370948b6ad78))


## v2.2.1 (2026-06-10)

### Bug Fixes

- **config**: Add default fallback for GITHUB_REPOSITORY
  ([#7](https://github.com/AhmedTyson/TeamsLeech-Bot/pull/7),
  [`e4f0718`](https://github.com/AhmedTyson/TeamsLeech-Bot/commit/e4f0718ee73f2925f2c5b9d3b0fb8297b9412e0a))


## v2.2.0 (2026-06-10)

### Bug Fixes

- Prevent MESSAGE_NOT_MODIFIED crash, pagination hang, and test failures
  ([`314e42d`](https://github.com/AhmedTyson/TeamsLeech-Bot/commit/314e42da304df63e23fa19a7f36ec9e63b3e5cc0))

- Remove spec=Message from AsyncMock in tests to resolve TypeError on await
  ([`27a4479`](https://github.com/AhmedTyson/TeamsLeech-Bot/commit/27a44798b989e3d637bd56697c4a908911e228f8))

- Rename thumb->thumb_path variable, add missing httpx import
  ([`25d3303`](https://github.com/AhmedTyson/TeamsLeech-Bot/commit/25d3303bc14dbe0672a77b32c8633705415ff1ff))

- Resolve edge cases in scanner, transfer handlers, and failing tests
  ([`9863017`](https://github.com/AhmedTyson/TeamsLeech-Bot/commit/9863017ac153a2afed1a1e15e45da74e0487e300))

- Resolve QUERY_ID_INVALID timeouts and test warnings
  ([#3](https://github.com/AhmedTyson/TeamsLeech-Bot/pull/3),
  [`4a70ca4`](https://github.com/AhmedTyson/TeamsLeech-Bot/commit/4a70ca47c2c06d1492909e4ad6dbeb91d5f59758))

### Build System

- Implement uv for deterministic and fast CI pipelines
  ([`391db76`](https://github.com/AhmedTyson/TeamsLeech-Bot/commit/391db76581011c02e4548f3d2f0aeeaac9db5c76))

### Chores

- Add missing __init__.py files to all subpackages
  ([`822bb57`](https://github.com/AhmedTyson/TeamsLeech-Bot/commit/822bb57d4fe1ac8d59380a6831966362310faf86))

### Code Style

- Fix ruff linting errors in handlers init and unit tests
  ([`9c45fd0`](https://github.com/AhmedTyson/TeamsLeech-Bot/commit/9c45fd076fd08d1e0156180d95c4a78012c37e63))

### Continuous Integration

- Configure git checkout with GH_PAT for semantic-release
  ([#6](https://github.com/AhmedTyson/TeamsLeech-Bot/pull/6),
  [`05c4101`](https://github.com/AhmedTyson/TeamsLeech-Bot/commit/05c410119f827de0c7a98f494f85ba2d88c33686))

- Use GH_PAT for semantic-release to bypass branch protection and fix config warning
  ([#5](https://github.com/AhmedTyson/TeamsLeech-Bot/pull/5),
  [`6b5e739`](https://github.com/AhmedTyson/TeamsLeech-Bot/commit/6b5e739b391294321d6de4d595089a03b0aff42e))

### Documentation

- Heavily update README for v2 architecture and remove obsolete files
  ([`93e01b0`](https://github.com/AhmedTyson/TeamsLeech-Bot/commit/93e01b063e272a37fe213bf11fee008489405c01))

- Remove obsolete generate_session script and marketing filler
  ([`c7af7e0`](https://github.com/AhmedTyson/TeamsLeech-Bot/commit/c7af7e0c33035feb80ec7d511357b0a5c167a5a9))

### Features

- Modernize state storage, add retry resilience, comprehensive test suite, CI coverage enforcement
  ([`b8aaaf3`](https://github.com/AhmedTyson/TeamsLeech-Bot/commit/b8aaaf33617f8ea2efc9fca6cde4a4dcbd486659))

- **ui**: Add /runner command to manage GitHub workflows
  ([#4](https://github.com/AhmedTyson/TeamsLeech-Bot/pull/4),
  [`26245c7`](https://github.com/AhmedTyson/TeamsLeech-Bot/commit/26245c701a565b1cae99344ddd3983d0d4f65666))

- **ui**: Improve team search results ux with pagination and full text
  ([#2](https://github.com/AhmedTyson/TeamsLeech-Bot/pull/2),
  [`040ec63`](https://github.com/AhmedTyson/TeamsLeech-Bot/commit/040ec6323c2501954586b262575d55581f07293b))

### Refactoring

- Resolve tech lead audit findings (SRP and typing)
  ([`fad5321`](https://github.com/AhmedTyson/TeamsLeech-Bot/commit/fad53218dc7a003c435ac75d0799c1ce55b45ce2))

### Testing

- Add unit tests for github_actions and actions_ui
  ([#4](https://github.com/AhmedTyson/TeamsLeech-Bot/pull/4),
  [`26245c7`](https://github.com/AhmedTyson/TeamsLeech-Bot/commit/26245c701a565b1cae99344ddd3983d0d4f65666))

- Add unit tests for telegram bot UI and handlers to increase coverage above 70%
  ([`5c75cac`](https://github.com/AhmedTyson/TeamsLeech-Bot/commit/5c75cacf4bbd842c63d2922a27dc8139ab8dbe0a))


## v2.1.0 (2026-06-09)

### Bug Fixes

- Add strict=True to zip, capture sem in closure default-arg
  ([`965712b`](https://github.com/AhmedTyson/TeamsLeech-Bot/commit/965712b94fea88d3fd2e5cf758fec572edb0cf39))

- Configure ruff src paths and fix remaining I001 import ordering
  ([`7c81990`](https://github.com/AhmedTyson/TeamsLeech-Bot/commit/7c81990e78c10a0aa6f6e95c0f741d852067acb7))

- Hardcode checkout ref to main in release.yml to close workflow_run privilege escalation
  ([`cd8c324`](https://github.com/AhmedTyson/TeamsLeech-Bot/commit/cd8c324858b776e105293d8a12aff1db2709ce24))

- Move exclude to [tool.ruff] top-level and add per-file-ignores for scripts/
  ([`ee6c43f`](https://github.com/AhmedTyson/TeamsLeech-Bot/commit/ee6c43fcebaf9d470c2987532706fd646c7e8d1e))

- Narrow except Exception to specific subprocess/json errors in _probe_video and _extract_thumbnail
  ([`0398716`](https://github.com/AhmedTyson/TeamsLeech-Bot/commit/0398716ebd5bdd9d56ce971078987ec891cbbafe))

- Narrow exception handling in transfer.py download/upload loops
  ([`f5fa705`](https://github.com/AhmedTyson/TeamsLeech-Bot/commit/f5fa705d109218566a4b15850734dd0c0979b412))

- Resolve B023 loop variable binding in closures in scanner.py and transfer.py
  ([`d180198`](https://github.com/AhmedTyson/TeamsLeech-Bot/commit/d180198d35142f9705cbfec34e5b0ecb4856d177))

- Test expects is_video auto-detection, fix format_duration for sub-minute durations
  ([`d0d9ef2`](https://github.com/AhmedTyson/TeamsLeech-Bot/commit/d0d9ef2e776c778e7520e5cee83717a2445cbe2c))

- Update release workflow to use semantic-release version command
  ([`b2faf56`](https://github.com/AhmedTyson/TeamsLeech-Bot/commit/b2faf56b349cedfcd946b880259a8b529af55869))

### Continuous Integration

- Auto-fix ruff issues before check so CI passes
  ([`fe5ae66`](https://github.com/AhmedTyson/TeamsLeech-Bot/commit/fe5ae668231b95d79bbaba9a003938773e1be9e9))

- Auto-format with ruff format so CI passes
  ([`721b518`](https://github.com/AhmedTyson/TeamsLeech-Bot/commit/721b5189479bb48b5a946d92b9ec27b0132c93b7))

- Run Release only after CI Pipeline succeeds on main
  ([`99ea2a0`](https://github.com/AhmedTyson/TeamsLeech-Bot/commit/99ea2a032773e3847dde77bc8975d55d28f2fcbe))

### Features

- Add file-type filter buttons (PDFs / Videos) to checklist keyboard
  ([`a83ad4a`](https://github.com/AhmedTyson/TeamsLeech-Bot/commit/a83ad4a80854e47ad8147653b750fd6b9fade66e))

- Migrate python-semantic-release config to v10 syntax
  ([`1cd4b2f`](https://github.com/AhmedTyson/TeamsLeech-Bot/commit/1cd4b2fffb2d11c02b7402138625daa1add9dc52))

### Refactoring

- Add video_count, doc_count, grouped_recordings properties to UserSession
  ([`c2017f4`](https://github.com/AhmedTyson/TeamsLeech-Bot/commit/c2017f42c45fa22fdc4e0e03fcfb74c110a5ed1d))

- Decouple StateManager from TransferService
  ([`952cdb9`](https://github.com/AhmedTyson/TeamsLeech-Bot/commit/952cdb9f1c3fa3d8429278d7b1d8d9f7cad1bfbe))

- Extract _consumer_loop from upload_recordings into class method
  ([`a9d85fb`](https://github.com/AhmedTyson/TeamsLeech-Bot/commit/a9d85fb68980913b98ac7e7803e987e26efcf4da))

- Extract _producer_loop from upload_recordings into class method
  ([`022e9d4`](https://github.com/AhmedTyson/TeamsLeech-Bot/commit/022e9d4b37ae55bc2346147d63e377b9956797a5))

- Extract progress reporting from nested closure into _report_progress method
  ([`a8ab6c6`](https://github.com/AhmedTyson/TeamsLeech-Bot/commit/a8ab6c611415168fa850c50a5f1803a71667df6c))

- Extract rename suggestion logic from UI handler into _get_rename_suggestion
  ([`57d4f52`](https://github.com/AhmedTyson/TeamsLeech-Bot/commit/57d4f52efb5b117c18f7b51232b7bdc516ccb332))

- Split build_checklist_keyboard into _build_toggle_rows, _build_upload_button, _build_filter_row,
  _build_action_row
  ([`49319ee`](https://github.com/AhmedTyson/TeamsLeech-Bot/commit/49319ee5b643e6a9326f9181f4c3e3ef212e5f7d))

- Split build_checklist_text into _build_header, _format_recording_item, _build_footer
  ([`22a3d7d`](https://github.com/AhmedTyson/TeamsLeech-Bot/commit/22a3d7db2e10210e1f3ed5f79fb5fbd96338aabb))


## v2.0.0 (2026-06-09)

### Bug Fixes

- Add blank lines between import groups to satisfy ruff I001
  ([`9df84bb`](https://github.com/AhmedTyson/TeamsLeech-Bot/commit/9df84bbae43911726116fcad88dac9084b5fddd3))

- Resolve 249 ruff lint errors across the codebase
  ([`4131875`](https://github.com/AhmedTyson/TeamsLeech-Bot/commit/41318756033eac80800d4dd16f6ccd9ac06e6b7c))

- Resolve remaining 93 ruff lint errors (import ordering, datetime.UTC, etc.)
  ([`4d3d390`](https://github.com/AhmedTyson/TeamsLeech-Bot/commit/4d3d3903bf421963cd321b35ed296387e4b4679c))

- **ci**: Add apt-get update before installing ffmpeg to prevent 404 errors
  ([`49f5028`](https://github.com/AhmedTyson/TeamsLeech-Bot/commit/49f50281efa241da27edf7aa88abb2a2c75772e9))

- **models**: Allow Team to be populated by field name (display_name) to fix pydantic validation
  error
  ([`a340b0e`](https://github.com/AhmedTyson/TeamsLeech-Bot/commit/a340b0e41b3114ccf65bb711eb37665190887ee6))

### Build System

- Phase 1 migration - replace requirements.txt with pyproject.toml, cleanup dead docs and broken
  tests, namespace src to teamsleech
  ([`8a6336b`](https://github.com/AhmedTyson/TeamsLeech-Bot/commit/8a6336b6dc92cceed7d7636e7cbacc0ddfffeebd))

### Chores

- Add issue/PR templates, Dependabot config, and CHANGELOG setup
  ([`f80cb45`](https://github.com/AhmedTyson/TeamsLeech-Bot/commit/f80cb45c485171a6a89cec9bfa17bc61806c00bd))

- Persist project architecture and stack to Serena Mem0
  ([`4792454`](https://github.com/AhmedTyson/TeamsLeech-Bot/commit/4792454a7e33e5109fe2cc5e0a7a4b94c88fceac))

- Remove Serena memories from version control and add to gitignore
  ([`cebd988`](https://github.com/AhmedTyson/TeamsLeech-Bot/commit/cebd9880d0cda3918c0e96a267ec05d2e83173e4))

### Code Style

- **ui**: Improve typography, spacing, and emojis across all telegram menus
  ([`1ccfa45`](https://github.com/AhmedTyson/TeamsLeech-Bot/commit/1ccfa45ded843c7b279a707cb690be4b1ad61e70))

### Continuous Integration

- Phase 2 - establish continuous integration pipeline with pytest, ruff, and mypy
  ([`8dfbecd`](https://github.com/AhmedTyson/TeamsLeech-Bot/commit/8dfbecd0728b524cdcbd4de9e2a83a7a97520dd4))

### Features

- Phase 3-4 — Semantic Release, GHA optimizations, bot resilience
  ([`aec86a4`](https://github.com/AhmedTyson/TeamsLeech-Bot/commit/aec86a424c337ca49b920fa28866f80aebf45327))

- **core**: Expand document scanning beyond PDF to include all standard academic formats (.pptx,
  .docx, .xlsx, .zip, .rar)
  ([`ed7d368`](https://github.com/AhmedTyson/TeamsLeech-Bot/commit/ed7d36812b3fd30ebf920a4a03611dab1e2bc531))

- **core**: Support scanning and uploading PDF documents alongside recordings
  ([`3841aeb`](https://github.com/AhmedTyson/TeamsLeech-Bot/commit/3841aeb83836c5f3978e5f0a931d20920bb65dea))

- **ui**: Add delete subject functionality directly from Telegram UI
  ([`c9a56c2`](https://github.com/AhmedTyson/TeamsLeech-Bot/commit/c9a56c29632c39ff9deb7548dd4457d43288972d))

- **ui**: Add inline keyboard for date selection and refine rename prompts
  ([`712ec8e`](https://github.com/AhmedTyson/TeamsLeech-Bot/commit/712ec8eaa4a5d80ed1c0625d594044649e04bcdb))

- **ui**: Interactive subject configuration to automatically update GitHub Secrets
  ([`572d439`](https://github.com/AhmedTyson/TeamsLeech-Bot/commit/572d439f6a16061b42ded957ccae865406940b74))

### Refactoring

- **core**: Implement modular architecture, Pydantic models, smart search, and silent auto-check
  ([`d84917f`](https://github.com/AhmedTyson/TeamsLeech-Bot/commit/d84917f0a565c536697c07fc84dc0ea2e005a13f))


## v1.0.0 (2026-06-09)

- Initial Release
