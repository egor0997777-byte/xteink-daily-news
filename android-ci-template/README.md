# Android CI template

Reusable GitHub Actions setup for Android projects.

Goal: avoid spending Codex runs on routine builds and visual checks.

## Two workflows

1. `android-build.yml.template` — cheap build-only workflow. Compiles a debug APK and uploads it as an artifact. Use this for routine verification.
2. `android-preview.yml.template` — heavier manual workflow. Starts an Android emulator, installs the APK, launches the app, captures a real emulator screenshot and uploads both the screenshot and APK.

The preview workflow is intentionally `workflow_dispatch` only so it does not consume emulator minutes on every commit.

## Per-project variables

For each Android app change only these values in the copied workflow:

- `APP_DIR` — project directory containing `gradlew`.
- `APK_PATH` — path to debug APK relative to repository root.
- `PACKAGE_NAME` — application ID.
- `MAIN_ACTIVITY` — launch activity, for example `.OcrMainActivity`.

## One-time installation

Copy the two `.template` files into `.github/workflows/` and remove the `.template` suffix.

The current ChatGPT GitHub connector cannot write workflow files, so this one-time copy should be performed by Codex or manually in GitHub. After that, normal builds/previews run entirely in GitHub Actions without Codex.

## Recommended use

- During coding: run `Android Build` when compilation needs checking.
- Before installing on a phone: run `Android Preview` and inspect the uploaded screenshot.
- Run emulator previews manually only when UI changed.

Current action versions were chosen from current upstream guidance: `actions/checkout@v6`, `actions/setup-java@v5`, `gradle/actions/setup-gradle@v6`, `ReactiveCircus/android-emulator-runner@v2.38.0`, and `actions/upload-artifact@v4`.
