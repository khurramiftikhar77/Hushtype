from hushtype.updater import parse_version, read_release

RELEASE = {
    "tag_name": "v0.3.0",
    "body": "New: Punjabi.",
    "html_url": "https://github.com/khurramiftikhar77/Hushtype/releases/tag/v0.3.0",
    "assets": [
        {"name": "notes.txt", "browser_download_url": "https://x/notes.txt", "size": 10},
        {"name": "Hushtype-Setup-0.3.0.exe", "browser_download_url": "https://x/setup.exe", "size": 77000000},
    ],
}


def test_parse_version():
    assert parse_version("v0.10.2") == (0, 10, 2)
    assert parse_version("0.2.0") < parse_version("0.10.0")


def test_newer_release_found():
    r = read_release(RELEASE, current="0.2.0")
    assert r["newer"] and r["latest"] == "0.3.0"
    assert r["asset_url"] == "https://x/setup.exe" and r["size"] == 77000000


def test_same_or_older_release_is_not_offered():
    assert not read_release(RELEASE, current="0.3.0")["newer"]
    assert not read_release(RELEASE, current="1.0.0")["newer"]


def test_release_without_installer():
    r = read_release({"tag_name": "v9.0.0", "assets": []}, current="0.2.0")
    assert r["newer"] and r["asset_url"] is None and not r["can_install"]
