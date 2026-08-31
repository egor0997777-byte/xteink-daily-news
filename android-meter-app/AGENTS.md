# Codex instructions — Мои счётчики

This folder is a standalone Android application.

## Role
The application logic, UX and product behavior are authored in the regular ChatGPT chat. Your role is to build, test, and make only the minimum changes required to obtain a working APK.

## Build target
- Android application module: `app`
- Application ID: `ru.egor.meters`
- Version: 0.4.0 (versionCode 4)
- Min SDK: 26
- Compile/target SDK: 37
- Android Gradle Plugin: 9.3.0
- Gradle: 9.5.0 or newer compatible version
- JDK: 17

## One-time GitHub Actions setup
The repository contains reusable templates in `android-ci-template/`.

On the next Codex run, before the normal build:
1. Copy `android-ci-template/android-build.yml.template` to `.github/workflows/android-build.yml`.
2. Copy `android-ci-template/android-preview.yml.template` to `.github/workflows/android-preview.yml`.
3. Preserve the workflow contents unless an actual GitHub Actions syntax/runtime error requires a minimal correction.
4. Commit/push those workflow files to branch `android-meter-app`.
5. After this one-time setup, routine APK builds and emulator screenshots should be run in GitHub Actions rather than consuming Codex runs.

The build workflow is intentionally manual and cheap. The preview workflow is intentionally manual and heavier: it boots an Android emulator, installs the APK, launches the app, captures a real screenshot, and uploads the screenshot plus APK as artifacts.

## Required procedure for source builds
1. Work only inside `android-meter-app/` unless a repository-level change is strictly required for the build or the one-time workflow setup above.
2. Inspect the current source before changing anything.
3. Do not redesign screens, data model, persistence, wording, colors, spacing, or behavior unless a confirmed compiler/runtime issue requires it.
4. Generate/repair the Gradle Wrapper if required.
5. Run `./gradlew :app:assembleDebug`.
6. If compilation fails, diagnose the exact error and make the smallest correction needed.
7. Re-run the build after every correction.
8. Stop only after `assembleDebug` succeeds or after identifying a blocker that cannot be fixed safely.
9. Report every source/config file you changed and the exact path to the resulting APK.

## v0.4 behavior and UX that must remain
- Multiple addresses and multiple meters per address.
- Dashboard counters for addresses, meters and readings.
- Clean light Apple-inspired visual language: airy layout, white cards, soft gray background, rounded corners, restrained purple accent.
- Meter presets: cold water, hot water, electricity, gas, heating, other.
- Optional meter serial number. Serial input accepts normal text keyboard for digits plus Russian/English letters and disables autocorrection.
- Reading input uses decimal keyboard and code-level filtering so only digits plus one decimal separator can be entered.
- Offline ML Kit OCR from the meter photo; recognized value remains user-editable before save.
- Manual readings with optional meter photo and note.
- Local persistence with backward compatibility for earlier data.
- Reading history and calculated consumption between consecutive readings.
- Warning for a reading lower than the previous reading, with an explicit meter-replacement override.
- Delete confirmation for addresses, meters and individual readings.
- No cloud account, analytics, ads or network requirement for recognition.
