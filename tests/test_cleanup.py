from hushtype.cleanup import clean


def test_removes_fillers():
    assert clean("Um, I think, uh, we should meet tomorrow.") == "I think, we should meet tomorrow."


def test_keeps_real_words_containing_filler_letters():
    assert clean("The umbrella is under the hummingbird.") == "The umbrella is under the hummingbird."


def test_capitalizes_after_filler_at_start():
    assert clean("uh thanks for sharing this.") == "Thanks for sharing this."


def test_replacements_case_insensitive():
    assert clean("Great post on linked in.", replacements={"linked in": "LinkedIn"}) == "Great post on LinkedIn."


def test_fillers_can_be_disabled():
    assert clean("Um, hello.", fillers=False) == "Um, hello."


def test_empty():
    assert clean("   ") == ""
