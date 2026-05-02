package com.mediaarchive

import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.mediaarchive.data.AppContainer
import com.mediaarchive.ui.screens.*
import com.mediaarchive.ui.theme.ArchiveTheme
import com.mediaarchive.viewmodel.ArtworkDetailViewModel
import com.mediaarchive.viewmodel.GalleryViewModel
import com.mediaarchive.viewmodel.ReviewQueueViewModel

@Composable
fun App() {
    ArchiveTheme {
        val navController = rememberNavController()
        val api = AppContainer.apiClient

        NavHost(navController = navController, startDestination = "gallery") {

            composable("gallery") {
                val vm = remember { GalleryViewModel(api) }
                GalleryScreen(
                    viewModel = vm,
                    onArtworkClick = { id -> navController.navigate("detail/$id") },
                    onQueueClick = { navController.navigate("queue") },
                    onSettingsClick = { navController.navigate("settings") },
                )
            }

            composable("detail/{artworkId}") { backStack ->
                val id = backStack.arguments?.get("artworkId")?.toString()?.toIntOrNull() ?: return@composable
                val vm = remember(id) { ArtworkDetailViewModel(api, id) }
                ArtworkDetailScreen(viewModel = vm, onBack = { navController.popBackStack() })
            }

            composable("queue") {
                val vm = remember { ReviewQueueViewModel(api) }
                ReviewQueueScreen(viewModel = vm, onBack = { navController.popBackStack() })
            }

            composable("settings") {
                SettingsScreen(onBack = { navController.popBackStack() })
            }
        }
    }
}
