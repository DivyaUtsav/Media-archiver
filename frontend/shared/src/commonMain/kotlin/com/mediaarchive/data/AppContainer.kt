package com.mediaarchive.data

import com.mediaarchive.data.api.ApiClient
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow

/**
 * Application-level container holding the ApiClient and current backend URL.
 * The URL is read lazily on each API call, so settings changes take effect
 * on the next request without restarting the app.
 */
object AppContainer {
    private val _backendUrl = MutableStateFlow(SettingsStore.getBackendUrl())
    val backendUrl: StateFlow<String> = _backendUrl

    val apiClient = ApiClient(baseUrl = { _backendUrl.value })

    fun updateBackendUrl(url: String) {
        val clean = url.trimEnd('/')
        SettingsStore.setBackendUrl(clean)
        _backendUrl.value = clean
    }
}
