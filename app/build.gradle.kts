plugins {
    id("com.android.application")
}

android {
    namespace = "com.burnilab.hollowwatchface"
    compileSdk = 36

    defaultConfig {
        applicationId = "com.burnilab.hollowwatchface"
        // RadixWatchFace hit a real Play upload rejection requiring
        // minSdk>=36 for any watch face using WeightedStroke-under-Arc
        // (used here for the star-field dots) -- set to 36 from the start
        // rather than rediscovering the same error.
        minSdk = 36
        targetSdk = 36
        versionCode = 1
        versionName = "1.0"
    }

    buildTypes {
        release {
            // Play rejects any release bundle containing a dex file at all,
            // even with hasCode="false" -- R8 shrinking strips the
            // auto-generated R/BuildConfig stub down to nothing. See
            // RadixWatchFace/SETUP.md for the full story.
            isMinifyEnabled = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"))
        }
    }
}
// No dependencies: a pure Watch Face Format package has no code.
