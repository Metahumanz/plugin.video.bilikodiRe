"""Small, testable policies for Kodi home-screen playback behavior."""


HOME_WINDOW_ID = 10000


def should_stop_video_on_home(
    window_id, previous_window_id, is_playing_video, enabled=True
):
    """Return whether an active video should stop on a transition into Home."""
    return bool(
        enabled
        and is_playing_video
        and window_id == HOME_WINDOW_ID
        and previous_window_id != HOME_WINDOW_ID
    )


__all__ = ["HOME_WINDOW_ID", "should_stop_video_on_home"]
