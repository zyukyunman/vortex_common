from pathlib import Path
import vortextool.cli as cli

COMMON = Path(cli.__file__).resolve().parent.parent


def test_image_base_wraps_script():
    argv = cli.build_image_argv("base", ["--no-cache"])
    assert argv[0] == str(COMMON / "scripts" / "build-base-image.sh")
    assert "--no-cache" in argv


def test_image_pull_and_build_wrap_deploy_scripts():
    assert cli.build_image_argv("pull", [])[0] == str(COMMON / "deploy" / "pull-code.sh")
    b = cli.build_image_argv("build", ["--tag=2026.06.10"])
    assert b[0] == str(COMMON / "deploy" / "build-release.sh")
    assert "--tag=2026.06.10" in b


def test_image_push_maps_to_build_release_push():
    argv = cli.build_image_argv("push", [])
    assert argv[0] == str(COMMON / "deploy" / "build-release.sh")
    assert "--push" in argv
