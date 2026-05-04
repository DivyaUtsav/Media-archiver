package com.mediaarchive.data

import android.content.Context
import android.content.SharedPreferences

/**
 * Android actual — uses SharedPreferences for persistent backend URL storage.
 *
 * Call [SettingsStore.init] from Application.onCreate() or MainActivity.onCreate()
 * before the first [getBackendUrl] / [setBackendUrl] call.
 */
actual object SettingsStore {
    private const val PREFS_NAME = "media_archive_prefs"
    private const val KEY_BACKEND_URL = "backend_url"
    private const val DEFAULT_URL = "http://10.0.2.2:8000"

    private var prefs: SharedPreferences? = null

    /** Must be called once (e.g. from MainActivity.onCreate) before use. */
    fun init(context: Context) {
        if (prefs == null) {
            prefs = context.applicationContext
                .getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        }
    }

    actual fun getBackendUrl(): String =
        prefs?.getString(KEY_BACKEND_URL, DEFAULT_URL) ?: DEFAULT_URL

    actual fun setBackendUrl(url: String) {
        prefs?.edit()?.putString(KEY_BACKEND_URL, url)?.apply()
    }
}
