package com.mediaarchive.data

/** Platform-specific persistence for user settings. */
expect object SettingsStore {
    fun getBackendUrl(): String
    fun setBackendUrl(url: String)
}
