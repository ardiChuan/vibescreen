plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "se.torget.vibepulse"
    compileSdk = 34

    defaultConfig {
        applicationId = "se.torget.vibepulse"
        // The Poco F3 shipped on Android 11 and takes 13; 26 covers it with
        // room to spare and keeps the Bluetooth permission split simple.
        minSdk = 26
        targetSdk = 34
        versionCode = 1
        versionName = "1.0.0"
    }

    buildTypes {
        release {
            isMinifyEnabled = false
        }
        debug {
            // The shelf build is the debug build: it installs over USB without
            // a release keystore, which is what "deploy to my own phone" needs.
            isMinifyEnabled = false
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
        // HorizontalPager and rememberPagerState still carry the experimental
        // marker in this Compose release. The panel is a pager of eight views,
        // so this is the API the design needs rather than an incidental use.
        freeCompilerArgs += "-opt-in=androidx.compose.foundation.ExperimentalFoundationApi"
    }
    buildFeatures {
        compose = true
    }
    composeOptions {
        kotlinCompilerExtensionVersion = "1.5.14"
    }
    packaging {
        resources.excludes += "/META-INF/{AL2.0,LGPL2.1}"
    }
    testOptions {
        unitTests {
            isIncludeAndroidResources = true
            isReturnDefaultValues = true
        }
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.4")
    implementation("androidx.activity:activity-compose:1.9.1")
    implementation(platform("androidx.compose:compose-bom:2024.06.00"))
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-graphics")
    implementation("androidx.compose.foundation:foundation")
    implementation("androidx.compose.material3:material3")

    testImplementation("junit:junit:4.13.2")
    // org.json is stubbed to throw in unit tests by default; the real
    // implementation makes the fixture tests meaningful.
    testImplementation("org.json:json:20240303")
}
