# Codex instructions — Мои счётчики

This folder is a standalone Android application.

## Role
The application logic and architecture are authored in the regular ChatGPT chat. Your role is to build, run, test, and make only the minimum changes required to obtain a working APK.

## Build target
- Android application module: `app`
- Application ID: `ru.egor.meters`
- Min SDK: 26
- Compile/target SDK: 37
- Android Gradle Plugin: 9.3.0
- Gradle: 9.5.0 or newer compatible version
- JDK: 17

## Required procedure
1. Work only inside `android-meter-app/` unless a repository-level change is strictly required for the build.
2. Inspect the current source before changing anything.
3. Do not redesign screens, data model, persistence, or application behavior.
4. Generate a Gradle Wrapper using Gradle 9.5.0 if the wrapper is absent.
5. Run `./gradlew :app:assembleDebug`.
6. If compilation fails, diagnose the exact error and make the smallest correction needed.
7. Re-run the build after every correction.
8. Stop only after `assembleDebug` succeeds or after identifying a blocker that cannot be fixed safely.
9. Report the exact path to the resulting APK.

## MVP behavior that must remain
- Multiple addresses.
- Multiple meters per address.
- Meter name and unit.
- Manual readings.
- Optional photo captured when adding a reading.
- Local persistence on device.
- Reading history.
- Difference between the latest two readings.
- Reject a new reading smaller than the previous one.
