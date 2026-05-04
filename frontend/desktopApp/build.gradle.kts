import org.jetbrains.compose.desktop.application.dsl.TargetFormat

plugins {
    alias(libs.plugins.kotlin.multiplatform)
    alias(libs.plugins.compose.multiplatform)
    alias(libs.plugins.compose.compiler)
}


kotlin {
    jvm()
    sourceSets {
        val jvmMain by getting {
            dependencies {
                implementation(project(":shared"))
                implementation(compose.desktop.currentOs)
                
                // FORCE matching Skiko native library version. Coil 3.1.0 pulls in Skiko 0.8.18,
                // but Compose 1.7.3 pulls in 0.9.4.2. Gradle upgrades the jar but fails to upgrade
                // the native runtime DLL, causing UnsatisfiedLinkError for RenderNodeContext_nMake.
                implementation("org.jetbrains.skiko:skiko-awt-runtime-windows-x64:0.9.4.2")
            }
        }
    }
}

compose.desktop {
    application {
        mainClass = "com.mediaarchive.MainKt"

        nativeDistributions {
            targetFormats(TargetFormat.Exe, TargetFormat.Msi)
            packageName = "MediaArchive"
            packageVersion = "1.0.0"
            includeAllModules = true
            description = "Personal Media Archive Desktop Client"
            vendor = "MediaArchive"
            windows {
                menuGroup = "Media Archive"
                upgradeUuid = "3a8b1e2f-4c5d-6e7f-8a9b-0c1d2e3f4a5b"
                console = true
            }
        }
    }
}

