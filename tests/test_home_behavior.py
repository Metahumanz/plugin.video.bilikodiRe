import unittest

from resources.lib.home_behavior import HOME_WINDOW_ID, should_stop_video_on_home


class HomeBehaviorTests(unittest.TestCase):
    def test_active_video_stops_only_on_kodi_home(self):
        self.assertTrue(should_stop_video_on_home(HOME_WINDOW_ID, 12005, True))
        self.assertFalse(should_stop_video_on_home(12005, HOME_WINDOW_ID, True))
        self.assertFalse(
            should_stop_video_on_home(HOME_WINDOW_ID, 12005, False)
        )
        self.assertFalse(
            should_stop_video_on_home(
                HOME_WINDOW_ID, 12005, True, enabled=False
            )
        )

    def test_starting_video_from_home_is_not_treated_as_returning_home(self):
        self.assertFalse(
            should_stop_video_on_home(HOME_WINDOW_ID, HOME_WINDOW_ID, True)
        )


if __name__ == "__main__":
    unittest.main()
