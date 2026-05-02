package com.mediaarchive.ui.screens

import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.mediaarchive.data.AppContainer

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsScreen(onBack: () -> Unit) {
    val currentUrl by AppContainer.backendUrl.collectAsState()
    var draftUrl by remember(currentUrl) { mutableStateOf(currentUrl) }
    var saved by remember { mutableStateOf(false) }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Settings") },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = MaterialTheme.colorScheme.surface),
            )
        },
    ) { padding ->
        Column(
            modifier = Modifier
                .padding(padding)
                .padding(24.dp)
                .fillMaxWidth(),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            Text("Backend Connection", style = MaterialTheme.typography.titleMedium)
            Text(
                "Enter the base URL of your FastAPI server. " +
                    "Use http://127.0.0.1:8000 for a local server, " +
                    "or your machine's LAN IP for remote / Android access.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            OutlinedTextField(
                value = draftUrl,
                onValueChange = { draftUrl = it; saved = false },
                label = { Text("Backend URL") },
                placeholder = { Text("http://127.0.0.1:8000") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )
            Button(
                onClick = {
                    AppContainer.updateBackendUrl(draftUrl)
                    saved = true
                },
                enabled = draftUrl.isNotBlank() && draftUrl != currentUrl || !saved,
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text(if (saved) "Saved ✓" else "Save")
            }

            if (saved) {
                Text(
                    "URL saved. All new requests will use the updated address.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.primary,
                )
            }

            Spacer(Modifier.height(24.dp))
            HorizontalDivider()
            Spacer(Modifier.height(8.dp))

            Text("About", style = MaterialTheme.typography.titleMedium)
            Text("Personal Media Archive — desktop client", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}
