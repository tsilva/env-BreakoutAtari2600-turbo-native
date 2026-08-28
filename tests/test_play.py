from __future__ import annotations

import sys
from types import SimpleNamespace

import env_breakoutatari2600_turbo_native.play as play
import numpy as np
import pytest
from env_breakoutatari2600_turbo_native.play import (
    _hud_text,
    _limit_frame_rate,
    _print_episode_stats,
    _scaled_frame_size,
    build_parser,
    run,
)


def test_play_parser_defaults_and_layout_selection():
    defaults = build_parser().parse_args([])
    assert defaults.layout == "full"
    assert defaults.scale == 4
    assert defaults.fps == 60
    assert defaults.frame_skip == 1
    assert defaults.show_obs is False
    assert defaults.uncapped is False
    selected = build_parser().parse_args(
        ["--layout", "tunnel", "--scale", "4", "--fps", "144", "--uncapped"]
    )
    assert selected.layout == "tunnel"
    assert selected.scale == 4
    assert selected.fps == 144
    assert selected.uncapped is True


def test_default_player_window_preserves_the_rendered_frame_aspect_ratio():
    assert _scaled_frame_size(160, 210, 4) == (640, 840)


def test_uncapped_mode_skips_the_frame_limiter():
    class Clock:
        calls: list[int] = []

        def tick(self, fps):
            self.calls.append(fps)

    clock = Clock()
    _limit_frame_rate(clock, 144)
    _limit_frame_rate(None, 144)
    assert clock.calls == [144]


def test_uncapped_play_remains_visible(monkeypatch):
    events: list[str] = []
    captions: list[str] = []

    class Screen:
        def blit(self, surface, position):
            events.append(f"blit:{position}")

    class Keys:
        def __getitem__(self, key):
            return False

    class FakeEnv:
        closed = False

        def __init__(self, **configuration):
            assert configuration["render_mode"] == "rgb_array"

        def reset(self, **kwargs):
            return np.zeros((1, 4, 84, 84), dtype=np.uint8), self.info()

        def step(self, action):
            return (
                np.zeros((1, 4, 84, 84), dtype=np.uint8),
                np.zeros(1, dtype=np.float32),
                np.zeros(1, dtype=np.bool_),
                np.zeros(1, dtype=np.bool_),
                self.info(),
            )

        def render(self):
            return np.zeros((210, 160, 3), dtype=np.uint8)

        def close(self):
            self.closed = True
            events.append("env.close")

        @staticmethod
        def info():
            return {
                "score": np.zeros(1, dtype=np.int64),
                "lives": np.full(1, 5, dtype=np.int64),
                "bricks_remaining": np.full(1, 108, dtype=np.int64),
                "walls_cleared": np.zeros(1, dtype=np.int64),
            }

    fake_pygame = SimpleNamespace(
        QUIT=1,
        KEYDOWN=2,
        K_ESCAPE=3,
        K_r=4,
        K_p=5,
        K_SPACE=6,
        K_LEFT=7,
        K_a=8,
        K_RIGHT=9,
        K_d=10,
        init=lambda: events.append("pygame.init"),
        quit=lambda: events.append("pygame.quit"),
        event=SimpleNamespace(get=lambda: []),
        key=SimpleNamespace(get_pressed=Keys),
        time=SimpleNamespace(
            Clock=lambda: pytest.fail("uncapped play must not create an FPS clock")
        ),
        display=SimpleNamespace(
            set_mode=lambda size: Screen(),
            set_caption=captions.append,
            flip=lambda: events.append("display.flip"),
        ),
        surfarray=SimpleNamespace(make_surface=lambda frame: object()),
        transform=SimpleNamespace(scale=lambda surface, size: surface),
    )
    monkeypatch.setitem(sys.modules, "pygame", fake_pygame)
    monkeypatch.setattr(play, "BreakoutVecEnv", FakeEnv)

    play.run(
        layout="full",
        scale=1,
        fps=144,
        frame_skip=1,
        max_frames=1,
        uncapped=True,
    )

    assert "blit:(0, 0)" in events
    assert events.count("display.flip") == 1
    assert any("uncapped" in caption for caption in captions)
    assert events[-2:] == ["env.close", "pygame.quit"]


def test_play_rejects_invalid_runtime_values():
    with pytest.raises(ValueError, match="positive"):
        run(layout="full", scale=0, fps=60, frame_skip=1, max_frames=1)


def test_episode_stats_are_printed(capsys):
    info = {
        "score": np.array([48]),
        "lives": np.array([2]),
        "bricks_remaining": np.array([0]),
        "walls_cleared": np.array([2]),
        "tick": np.array([1234]),
    }
    _print_episode_stats(
        info,
        episode=3,
        layout="full",
        episode_return=48.0,
        display_steps=309,
        elapsed=5.25,
    )
    output = capsys.readouterr().out
    assert "episode_end episode=3" in output
    assert "outcome=cleared" in output
    assert "score=48" in output
    assert "return=48.0" in output
    assert "walls_cleared=2" in output
    assert "bricks_remaining=0" in output
    assert "native_ticks=1234" in output


def test_hud_shows_score_lives_and_bricks():
    info = {
        "score": np.array([7]),
        "lives": np.array([2]),
        "bricks_remaining": np.array([41]),
        "walls_cleared": np.array([1]),
    }
    assert (
        _hud_text(info, paused=False)
        == "SCORE 007    LIVES 2    WALLS 1/2    BRICKS 41"
    )
    assert _hud_text(info, paused=True).endswith("PAUSED")
