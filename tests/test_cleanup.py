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


def test_new_paragraph_and_line():
    out = clean("Hi Sara, new paragraph. Thanks for the update. New line. Khurram")
    assert out == "Hi Sara,\n\nThanks for the update.\nKhurram"


def test_punctuation_words_are_kept_as_words():
    # Punctuation comes from Whisper automatically; saying "comma" is just a word.
    assert clean("Put a comma here.") == "Put a comma here."


def test_spoken_commands_can_be_disabled():
    assert clean("Write a new line here.", spoken_commands=False) == "Write a new line here."


def test_snippet_whole_dictation():
    snippets = {"my signature": "Best regards,\nKhurram"}
    assert clean("My signature.", snippets=snippets) == "Best regards,\nKhurram"


def test_snippet_inside_sentence():
    snippets = {"my email": "k@example.com"}
    assert clean("You can reach me at my email.", snippets=snippets) == "You can reach me at k@example.com"


def test_urdu_untouched_by_english_rules():
    text = "السلام علیکم، کل میٹنگ ہے۔"
    assert clean(text, language="ur") == text


def test_no_capitalize_option():
    assert clean("roses are red.\nviolets are blue.", capitalize=False) == "roses are red.\nviolets are blue."
