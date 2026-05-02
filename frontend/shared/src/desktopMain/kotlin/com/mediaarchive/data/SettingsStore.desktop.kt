package com.mediaarchive.data

import java.util.prefs.Preferences

actual object SettingsStore {
    private val prefs = Preferences.userRoot().node("com/mediaarchive")
    private const val KEY_BACKEND_URL = "backend_url"
    private const val DEFAULT_URL = "http://127.0.0.1:8000"

    actual fun getBackendUrl(): String = prefs.get(KEY_BACKEND_URL, DEFAULT_URL)
    actual fun setBackendUrl(url: String) { prefs.put(KEY_BACKEND_URL, url) }
}
