package com.mediaarchive

import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import androidx.navigation.toRoute
import com.mediaarchive.data.AppContainer
import com.mediaarchive.ui.screens.*
import com.mediaarchive.ui.theme.ArchiveTheme
import com.mediaarchive.viewmodel.ArtworkDetailViewModel
import com.mediaarchive.viewmodel.GalleryViewModel
import com.mediaarchive.viewmodel.ReviewQueueViewModel
import kotlinx.serialization.Serializable

// ── Type-safe route destinations ────────────────────────────────────────────

@Serializable
object GalleryRoute

@Serializable
data class DetailRoute(val artworkId: Int)

@Serializable
object QueueRoute

@Serializable
object SettingsRoute

// ── App entry point ──────────────────────────────────────────────────────────

@Composable
fun App() {
    ArchiveTheme {
        val navController = rememberNavController()
        val api = AppContainer.apiClient
        val galleryViewModel = viewModel { GalleryViewModel(api) }

        NavHost(navController = navController, startDestination = GalleryRoute) {

            composable<GalleryRoute> {
                GalleryScreen(
                    viewModel = galleryViewModel,
                    onArtworkClick = { id -> navController.navigate(DetailRoute(id)) },
                    onQueueClick = { navController.navigate(QueueRoute) },
                    onSettingsClick = { navController.navigate(SettingsRoute) },
                )
            }

            composable<DetailRoute> { backStack ->
                val route: DetailRoute = backStack.toRoute()
                val vm = remember(route.artworkId) { ArtworkDetailViewModel(api, route.artworkId) }
                ArtworkDetailScreen(
                    viewModel = vm, 
                    galleryViewModel = galleryViewModel,
                    onBack = { navController.popBackStack() },
                    onNavigate = { newId ->
                        navController.navigate(DetailRoute(newId)) {
                            popUpTo<DetailRoute> { inclusive = true }
                        }
                    }
                )
            }

            composable<QueueRoute> {
                val vm = remember { ReviewQueueViewModel(api) }
                ReviewQueueScreen(viewModel = vm, onBack = { navController.popBackStack() })
            }

            composable<SettingsRoute> {
                SettingsScreen(onBack = { navController.popBackStack() })
            }
        }
    }
}
