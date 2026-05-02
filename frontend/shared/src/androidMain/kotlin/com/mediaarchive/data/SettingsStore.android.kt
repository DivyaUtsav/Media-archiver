package com.mediaarchive.data

// Stub — Android commit will use DataStore or SharedPreferences.
actual object SettingsStore {
    actual fun getBackendUrl(): String = "http://10.0.2.2:8000"
    actual fun setBackendUrl(url: String) { /* TODO: Android commit */ }
}
