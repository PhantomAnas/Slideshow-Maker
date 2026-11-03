from slideshow_maker.cli import apply_args, build_parser, main
from slideshow_maker.settings import RenderSettings


def test_settings_round_trip(tmp_path):
    p = str(tmp_path / "s.json")
    s = RenderSettings(width=1280, height=720, transition="slide", background_rgb=(1, 2, 3),
                       logo_position="top-left", extra={"k": 1})
    s.save(p)
    back = RenderSettings.load(p)
    assert back == s and isinstance(back.background_rgb, tuple)


def test_settings_bad_file_and_unknown_keys(tmp_path):
    p = tmp_path / "s.json"
    p.write_text("{bad")
    assert RenderSettings.load(str(p)) == RenderSettings()
    p.write_text('{"fps": 24, "bogus": 1}')
    assert RenderSettings.load(str(p)).fps == 24


def test_validate_reports_problems(tmp_path):
    s = RenderSettings(width=10, fps=0, transition="wipe", logo_path=str(tmp_path / "no.png"), crf=99)
    msgs = " ".join(s.validate())
    for word in ("64x64", "fps", "transition", "logo", "crf"):
        assert word in msgs
    assert RenderSettings().validate() == []
    assert RenderSettings(width=1081, height=1919).even_size == (1080, 1918)


def test_apply_args_maps_flags():
    a = build_parser().parse_args(["--images", "pics", "--aspect", "16:9", "--per-image", "2",
                                   "--transition", "slide", "--videos", "3", "--music", "m.mp3",
                                   "--fit", "crop", "--size", "640x360"])
    s = apply_args(RenderSettings(), a)
    assert (s.source_folder, s.width, s.height) == ("pics", 640, 360)
    assert s.seconds_per_image == 2 and s.transition == "slide" and s.videos_count == 3
    assert s.music_path == "m.mp3" and s.fit == "crop"


def test_cli_requires_a_source(capsys):
    assert main(["--no-saved-settings"]) == 2
    assert "give --images" in capsys.readouterr().err


def test_cli_check_flag():
    rc = main(["--check"])
    assert rc in (0, 1)
