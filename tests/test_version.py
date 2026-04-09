from src.version import APP_NAME, APP_VERSION, INSTALLER_VERSION, build_about_text, to_installer_version


def test_app_version_format():
    assert APP_NAME == "iCloud to Synology Sync"
    assert APP_VERSION.count(".") == 2


def test_installer_version_matches_app_version():
    assert INSTALLER_VERSION == to_installer_version(APP_VERSION)
    assert INSTALLER_VERSION.count(".") == 3


def test_about_text_includes_version():
    about_text = build_about_text()
    assert APP_NAME in about_text
    assert APP_VERSION in about_text