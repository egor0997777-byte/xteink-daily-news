# Codex instructions — Мои счётчики

This folder is a standalone Android application.

## Role
The application logic and product behavior are authored in the regular ChatGPT chat. Your role is to build, test, and make only the minimum changes required to obtain a working APK.

## Build target
- Android application module: `app`
- Application ID: `ru.egor.meters`
- Version: 0.2.0 (versionCode 2)
- Min SDK: 26
- Compile/target SDK: 37
- Android Gradle Plugin: 9.3.0
- Gradle: 9.5.0 or newer compatible version
- JDK: 17

## Required procedure
1. Work only inside `android-meter-app/` unless a repository-level change is strictly required for the build.
2. Inspect the current source before changing anything.
3. Do not redesign screens, data model, persistence, wording, or behavior unless a confirmed compiler/runtime issue requires it.
4. Generate/repair the Gradle Wrapper if required.
5. Run `./gradlew :app:assembleDebug`.
6. If compilation fails, diagnose the exact error and make the smallest correction needed.
7. Re-run the build after every correction.
8. Stop only after `assembleDebug` succeeds or after identifying a blocker that cannot be fixed safely.
9. Report every source/config file you changed and the exact path to the resulting APK.

## v0.2 behavior that must remain
- Multiple addresses and multiple meters per address.
- Dashboard counters for addresses, meters and readings.
- Meter presets: cold water, hot water, electricity, gas, heating, other.
- Optional meter serial number.
- Manual readings with optional meter photo and note.
- Local persistence with backward compatibility for v0.1 data.
- Reading history and calculated consumption between consecutive readings.
- Warning for a reading lower than the previous reading, with an explicit meter-replacement override.
- Delete confirmation for addresses, meters and individual readings.
- No cloud account, analytics, ads or network requirement.
