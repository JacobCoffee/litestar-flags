# Changelog

All notable changes to this project will be documented in this file.

## [unreleased]


### Bug Fixes


- fix: checkout main branch in CD workflow for changelog push - ([92f334a](https://github.com/JacobCoffee/litestar-flags/commit/92f334a884b4229341cea80465ae98c175d744f3))

- fix: explicitly set remote URL with PAT for changelog push - ([18b836a](https://github.com/JacobCoffee/litestar-flags/commit/18b836a9e99f796cdf52bd6c94b93bd20f31cb97))

- fix: create PR instead of direct push for changelog updates - ([ecc2469](https://github.com/JacobCoffee/litestar-flags/commit/ecc24699b179a9bafafefb9452014d6f0bc4eeb8))

- fix: revert to direct push for changelog - ([95c0fd1](https://github.com/JacobCoffee/litestar-flags/commit/95c0fd1c22966f410cd6ead4a8e48f3883bd2d51))


### Documentation


- docs: regenerate changelog for v0.2.0 - ([9ac26ff](https://github.com/JacobCoffee/litestar-flags/commit/9ac26ffa9b9223046ab2a54de15ca41cbff7b03e))
## [0.2.0](https://github.com/JacobCoffee/litestar-flags/compare/v0.1.1..v0.2.0) - 2025-12-30


### Bug Fixes


- fix: use text lexer instead of http for code blocks in docs - ([56a038b](https://github.com/JacobCoffee/litestar-flags/commit/56a038baee4d8266fb3bf6038dca3ae3c5fc6630))

- fix: remove On This Page ToC and fix duplicate toctree refs - ([2354807](https://github.com/JacobCoffee/litestar-flags/commit/235480792c948eef057a37590c2a6a0e5ee2a821))


### Features


- feat: add segment-based targeting for reusable user groups (#2) - ([62ae7ce](https://github.com/JacobCoffee/litestar-flags/commit/62ae7cecea2ea25de611e7e25f1fcd71e15122b8))

- feat: add multi-environment support with inheritance and promotion - ([fe095f7](https://github.com/JacobCoffee/litestar-flags/commit/fe095f708e026e90f91dfb5ded9a5ef2c78d64b3))

- feat: add flag analytics module with evaluation tracking and metrics - ([026995c](https://github.com/JacobCoffee/litestar-flags/commit/026995c4c27d8be6c868a3b0f7d3222e9134debf))

- feat: add Admin API with REST endpoints for flag management - ([a9dfb20](https://github.com/JacobCoffee/litestar-flags/commit/a9dfb203ee46b7fa924a1dbfb506cc4e9667a600))

- feat: add CD workflow for changelog automation and update docs - ([d1de4ba](https://github.com/JacobCoffee/litestar-flags/commit/d1de4babf2896c2278d5ff5789f333b8a5a5ee6a))


### Miscellaneous Chores


- chore: add optional deps to docs group for autodoc type resolution - ([eeb82d5](https://github.com/JacobCoffee/litestar-flags/commit/eeb82d57227e68646c0da5c037ebdfb835deedfe))


### Refactoring


- refactor: rename AdminPlugin to FeatureFlagsAdminPlugin - ([fa97090](https://github.com/JacobCoffee/litestar-flags/commit/fa97090fc41e839e2da0c84deb358860ea1ba234))
## [0.1.1] - 2025-12-28


### Bug Fixes


- fix: resolve zizmor security scan findings - ([94f6c18](https://github.com/JacobCoffee/litestar-flags/commit/94f6c1814524e201f6397f8a832c555e97e7c35a))

- fix: remove local path override for litestar-workflows - ([e16ce98](https://github.com/JacobCoffee/litestar-flags/commit/e16ce98e43a6a276825a8a262c2a2910b38e7ecb))

- fix: move importlib import to top of file - ([db6ee09](https://github.com/JacobCoffee/litestar-flags/commit/db6ee094745d4444f8cfcd0815ebf9489a6ee374))

- fix: use longer TTL for Windows clock resolution compatibility - ([a9bb0c6](https://github.com/JacobCoffee/litestar-flags/commit/a9bb0c6aa778789c17ab1d7d49b17565fb626d32))

- fix: remove skip logic for otel tests - all extras should be installed - ([e09b647](https://github.com/JacobCoffee/litestar-flags/commit/e09b6479f2992202128a5b4f158e94e19419fb8b))

- fix: increase timeouts for Windows clock resolution - ([1caf061](https://github.com/JacobCoffee/litestar-flags/commit/1caf061fb291b0349d1439518c124dc5d52b8bca))

- fix: increase token bucket refill test sleep for Windows - ([30fbe99](https://github.com/JacobCoffee/litestar-flags/commit/30fbe9941f8e47d9c8fe1166f6200c85d70f99a6))

- fix: add missing linkify-it-py for docs build - ([315f2fc](https://github.com/JacobCoffee/litestar-flags/commit/315f2fc08e234cfe6156cf9cdac98cfbe9dbaf07))

- fix: add pyproject.toml to docs workflow trigger paths - ([a1d42c3](https://github.com/JacobCoffee/litestar-flags/commit/a1d42c321aece9f58f57ba0d2566f80bff82a322))


### Miscellaneous Chores


- chore: add project CLAUDE.md, use prek, fix type exclusions and tests - ([868f5ff](https://github.com/JacobCoffee/litestar-flags/commit/868f5ff194b8e2698f50d49371f9da6773edac6b))

- chore: add git-cliff configuration and initial changelog - ([4d84cf6](https://github.com/JacobCoffee/litestar-flags/commit/4d84cf6ce0c69b9033e4bc2a8b15255f3d0ffe87))

- chore: bump version to 0.1.1 - ([fe020fb](https://github.com/JacobCoffee/litestar-flags/commit/fe020fb163109cc46fb3ebf313e787522638ae6e))


### Style


- style: apply ruff formatting - ([1dd97ea](https://github.com/JacobCoffee/litestar-flags/commit/1dd97ea211ac6c371e639cfcb7f3d71d3c30333e))
---
*litestar-flags Changelog*
