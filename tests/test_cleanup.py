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


# ---------- self-correction ----------

def test_no_wait_replaces_the_word_before():
    assert clean("Let's meet on Monday, no wait, Tuesday.") == "Let's meet on Tuesday."


def test_sorry_i_mean_replaces_same_number_of_words():
    assert clean("Call me at 3 pm, sorry, I mean 4 pm.") == "Call me at 4 pm."


def test_correction_stops_at_comma():
    assert clean("See you Monday, no wait, Tuesday, at the office.") == "See you Tuesday, at the office."


def test_scratch_that_removes_previous_sentence():
    assert clean("I will send it tomorrow. Scratch that. I will send it today.") == "I will send it today."


def test_normal_i_mean_is_kept():
    # plain "I mean" is common in speech and is not treated as a correction
    assert clean("I mean, it was a great talk.") == "I mean, it was a great talk."


# ---------- lists and email ----------

def test_numbered_list():
    text = "Three things to do. First, update the report. Second, call Sara. Finally, send the invoice."
    assert clean(text) == "Three things to do.\n1. Update the report.\n2. Call Sara.\n3. Send the invoice."


def test_single_first_is_not_a_list():
    assert clean("First, thank you for the invite.") == "First, thank you for the invite."


def test_email_layout_only_when_asked():
    text = "Hi Ahmed, thanks for the proposal. Can we talk on Thursday? Best regards, Khurram"
    assert clean(text) == text
    assert clean(text, email=True) == "Hi Ahmed,\n\nThanks for the proposal. Can we talk on Thursday?\n\nBest regards,\nKhurram"


def test_email_signoff_without_name():
    assert clean("Hello team, the report is attached. Thanks", email=True) == "Hello team,\n\nThe report is attached.\n\nThanks,"
