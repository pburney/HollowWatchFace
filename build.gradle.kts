// Root build file. AGP 8.5+ needs JDK 17+ (you have 21). Pinned to 8.7.3 --
// see RadixWatchFace's build.gradle.kts for why (SDK schema version
// mismatch with older AGP against the installed android-37.0 platform).
plugins {
    id("com.android.application") version "8.7.3" apply false
}
