package com.mediaarchive.data.api

import io.ktor.client.*
import io.ktor.client.engine.cio.*
import io.ktor.client.plugins.contentnegotiation.*
import io.ktor.client.plugins.logging.*
import io.ktor.serialization.kotlinx.json.*
import kotlinx.serialization.json.Json

actual fun createPlatformHttpClient(json: Json): HttpClient = HttpClient(CIO) {
    install(ContentNegotiation) { json(json) }
    install(Logging) { level = LogLevel.INFO }
}
